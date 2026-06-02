from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_agent_graph_stream, run_agent_graph_sync
from app.api.middleware import get_current_user, get_current_user_optional, ok
from app.database.connection import get_db
from app.database.models import QuerySession, User
from app.schemas.query import QueryRequest, QuerySessionDetail, QuerySessionSummary
from app.utils.guardrails import validate_query

logger = logging.getLogger(__name__)
router = APIRouter()


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
    session_id = request.session_id or str(uuid.uuid4())
    user_id = current_user.id if current_user else None
    t0 = time.perf_counter()

    async def event_generator():
        all_trace: list = []
        final_event: dict = {}

        try:
            async for event in run_agent_graph_stream(
                query=validated_query,
                session_id=session_id,
                user_id=user_id or "anonymous",
                filters=request.filters,
            ):
                all_trace.append(event)
                if event.get("type") == "final_result":
                    final_event = event
                yield f"data: {json.dumps(event, default=str)}\n\n"

        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=True)
            error_event = {
                "type": "error",
                "agent": "system",
                "data": {"error": str(exc)},
            }
            yield f"data: {json.dumps(error_event)}\n\n"
            return

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
