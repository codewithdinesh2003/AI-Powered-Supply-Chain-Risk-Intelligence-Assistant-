from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_agent_graph_stream, run_agent_graph_sync
from app.api.middleware import get_current_user, get_current_user_optional, ok
from app.database.connection import get_db
from app.database.models import QueryFeedback, QuerySession, User
from app.schemas.query import QueryRequest, QuerySessionDetail, QuerySessionSummary
from app.utils.guardrails import validate_query

logger = logging.getLogger(__name__)
router = APIRouter()

_PIPELINE_TIMEOUT_S = 90   # hard kill if entire pipeline exceeds this

# ── In-memory query cache (TTL 10 min) ───────────────────────────────────────
_query_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
_CACHE_TTL = 600   # seconds

def _cache_key(query: str, filters: Optional[Dict] = None) -> str:
    raw = query.lower().strip() + json.dumps(filters or {}, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()

def _get_cached(key: str) -> Optional[Dict[str, Any]]:
    entry = _query_cache.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    if entry:
        del _query_cache[key]
    return None

def _set_cache(key: str, data: Dict[str, Any]) -> None:
    _query_cache[key] = (data, time.time() + _CACHE_TTL)


# ── Save session helper ───────────────────────────────────────────────────────

async def _save_session(
    db: AsyncSession,
    session_id: str,
    user_id: Optional[str],
    query_text: str,
    final_event: dict,
    all_trace_events: list,
    start_ms: int,
) -> None:
    data = final_event.get("data", {})
    elapsed = final_event.get("total_elapsed_ms", 0)
    tokens = final_event.get("tokens_used", 0)
    eval_scores = data.get("evaluation_scores", {})
    overall_score = eval_scores.get("overall_score") if eval_scores else None

    session = QuerySession(
        id=str(uuid.uuid4()),
        session_id=session_id,
        user_id=user_id,
        query_text=query_text,
        agent_trace={"events": all_trace_events},
        retrieval_context=None,
        result={
            "recommendations": data.get("recommendations", []),
            "risk_score": data.get("risk_score"),
            "final_response": data.get("final_response"),
        },
        tokens_used=tokens,
        latency_ms=elapsed,
        evaluation_score=float(overall_score) if overall_score is not None else None,
        deepeval_scores=eval_scores or None,
    )
    db.add(session)
    await db.commit()
    logger.info("Query session saved: %s", session_id)


# ── Streaming SSE endpoint ────────────────────────────────────────────────────

@router.post("/stream")
async def stream_query(
    request: QueryRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Main query endpoint — streams SSE agent events as the graph executes."""
    validated_query = validate_query(request.query)
    session_id      = request.session_id or str(uuid.uuid4())
    user_id         = current_user.id if current_user else None
    t0              = time.perf_counter()
    cache_key       = _cache_key(validated_query, request.filters)

    async def event_generator():
        all_trace: list = []
        final_event: dict = {}

        # ── Cache hit: serve instantly without running the pipeline ─────
        cached = _get_cached(cache_key)
        if cached:
            logger.info("Cache hit for query: %s", validated_query[:60])
            now = datetime.now(timezone.utc).isoformat()
            # Mark all agents done immediately
            for agent_name in ("retrieval", "supplier_risk", "shipment_analysis",
                               "inventory_intel", "recommendation", "evaluator"):
                yield f"data: {json.dumps({'type':'agent_started','agent':agent_name,'data':{'message':'Serving from cache'},'timestamp':now})}\n\n"
                yield f"data: {json.dumps({'type':'agent_completed','agent':agent_name,'data':{'message':'Cached result'},'timestamp':now})}\n\n"

            cache_event = {
                "type":      "cache_hit",
                "agent":     "system",
                "data":      cached,
                "timestamp": now,
                "from_cache": True,
            }
            yield f"data: {json.dumps(cache_event, default=str)}\n\n"

            final_result_event = {
                "type":             "final_result",
                "agent":            "system",
                "data":             cached,
                "timestamp":        now,
                "total_elapsed_ms": 0,
                "tokens_used":      0,
                "from_cache":       True,
            }
            yield f"data: {json.dumps(final_result_event, default=str)}\n\n"
            yield f"data: {json.dumps({'type':'pipeline_done','agent':'system','data':{},'timestamp':now})}\n\n"
            return

        # ── Live run with total timeout ───────────────────────────────────
        try:
            # asyncio.timeout() is a context manager in Python 3.11+
            async with asyncio.timeout(_PIPELINE_TIMEOUT_S):
                async for event in run_agent_graph_stream(
                    query=validated_query,
                    session_id=session_id,
                    user_id=user_id or "anonymous",
                    filters=request.filters,
                ):
                    all_trace.append(event)
                    if event.get("type") == "final_result":
                        final_event.update(event)
                    yield f"data: {json.dumps(event, default=str)}\n\n"

        except TimeoutError:
            logger.error("Pipeline timed out after %ss", _PIPELINE_TIMEOUT_S)
            yield f"data: {json.dumps({'type':'error','agent':'system','data':{'error':f'Pipeline timed out after {_PIPELINE_TIMEOUT_S}s'}})}\n\n"
            return
        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type':'error','agent':'system','data':{'error':str(exc)}})}\n\n"
            return

        # Cache the result for future identical queries
        if final_event:
            _set_cache(cache_key, final_event.get("data", {}))

        # Persist session to MySQL after streaming completes
        try:
            await _save_session(
                db=db,
                session_id=session_id,
                user_id=user_id,
                query_text=validated_query,
                final_event=final_event,
                all_trace_events=all_trace,
                start_ms=int((time.perf_counter() - t0) * 1000),
            )
        except Exception as exc:
            logger.warning("Session save failed (non-fatal): %s", exc)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "X-Session-Id": session_id,
        },
    )


# ── Synchronous endpoint ──────────────────────────────────────────────────────

@router.post("/sync")
async def sync_query(
    request: QueryRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming version — waits for full graph and returns JSON."""
    validated_query = validate_query(request.query)
    session_id = request.session_id or str(uuid.uuid4())
    user_id = current_user.id if current_user else None
    t0 = time.perf_counter()

    final_state = await run_agent_graph_sync(
        query=validated_query,
        session_id=session_id,
        user_id=user_id or "anonymous",
        filters=request.filters,
    )

    elapsed = int((time.perf_counter() - t0) * 1000)

    result = {
        "session_id": session_id,
        "query": validated_query,
        "recommendations": final_state.get("recommendations", []),
        "risk_score": final_state.get("risk_score"),
        "final_response": final_state.get("final_response"),
        "evaluation_scores": final_state.get("evaluation_scores"),
        "retrieved_incidents": final_state.get("retrieved_incidents", []),
        "agent_trace": final_state.get("agent_trace", []),
        "tokens_used": final_state.get("tokens_used", 0),
        "elapsed_ms": elapsed,
        "errors": final_state.get("errors", []),
    }

    # Persist
    try:
        eval_scores = final_state.get("evaluation_scores") or {}
        session = QuerySession(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            query_text=validated_query,
            agent_trace={"events": final_state.get("agent_trace", [])},
            result={
                "recommendations": result["recommendations"],
                "risk_score": result["risk_score"],
                "final_response": result["final_response"],
            },
            tokens_used=result["tokens_used"],
            latency_ms=elapsed,
            evaluation_score=eval_scores.get("overall_score"),
            deepeval_scores=eval_scores or None,
        )
        db.add(session)
        await db.commit()
    except Exception as exc:
        logger.warning("Session save failed: %s", exc)

    return ok(result, meta={"elapsed_ms": elapsed, "session_id": session_id})


# ── Query history ─────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(QuerySession)
        .where(QuerySession.user_id == current_user.id)
        .order_by(QuerySession.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    return ok(
        [QuerySessionSummary.model_validate(s).model_dump() for s in sessions],
        meta={"skip": skip, "limit": limit},
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(QuerySession)
        .where(QuerySession.session_id == session_id, QuerySession.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return ok(QuerySessionDetail.model_validate(session).model_dump())


@router.post("/sessions/{session_id}/feedback", status_code=201)
async def submit_feedback(
    session_id: str,
    rating:  int  = Body(..., ge=1, le=5),
    helpful: bool = Body(...),
    comment: str  = Body(""),
    db: AsyncSession = Depends(get_db),
):
    fb = QueryFeedback(
        id=str(uuid.uuid4()),
        session_id=session_id,
        overall_rating=rating,
        helpful=helpful,
        comment=comment or None,
    )
    db.add(fb)
    await db.commit()
    return ok({"submitted": True})
