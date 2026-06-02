from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware import get_current_user, ok
from app.database.connection import get_db
from app.database.models import EvaluationResult, JudgeVerdict, QuerySession, User
from app.schemas.observability import EvaluationResultResponse

logger = logging.getLogger(__name__)
router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)


# ── DeepEval runner (sync, runs in thread pool) ───────────────────────────────

def _run_deepeval(query: str, response: str, context: List[str]) -> dict:
    try:
        from deepeval import evaluate
        from deepeval.metrics import (
            AnswerRelevancyMetric,
            ContextualRecallMetric,
            FaithfulnessMetric,
        )
        from deepeval.test_case import LLMTestCase

        test_case = LLMTestCase(
            input=query,
            actual_output=response,
            retrieval_context=context[:5],  # cap to 5 docs
        )
        metrics = [
            AnswerRelevancyMetric(threshold=0.7, model="gpt-4o", async_mode=False),
            FaithfulnessMetric(threshold=0.8, model="gpt-4o", async_mode=False),
            ContextualRecallMetric(threshold=0.7, model="gpt-4o", async_mode=False),
        ]
        evaluate([test_case], metrics, run_async=False, print_results=False)

        return {
            "answer_relevancy": getattr(metrics[0], "score", None),
            "faithfulness": getattr(metrics[1], "score", None),
            "contextual_recall": getattr(metrics[2], "score", None),
            "contextual_precision": None,
            "success": True,
        }
    except Exception as exc:
        logger.warning("DeepEval evaluation failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ── Schemas ──────────────────────────────────────────────────────────────────

class EvaluationRunRequest(BaseModel):
    session_id: str
    query: Optional[str] = None
    response: Optional[str] = None
    context: Optional[List[str]] = None


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_evaluation(
    req: EvaluationRunRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Trigger DeepEval + LLM-judge evaluation for a query session."""
    # Fetch session to get query/response/context if not provided
    session = None
    if not (req.query and req.response):
        result = await db.execute(
            select(QuerySession).where(QuerySession.session_id == req.session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found.")

    query = req.query or (session.query_text if session else "")
    result_data = (session.result or {}) if session else {}
    response = req.response or result_data.get("final_response", "")
    context_docs = req.context
    if context_docs is None and session:
        retrieval = session.retrieval_context or {}
        context_docs = [d.get("text", "") for d in retrieval.get("documents", [])][:5]
    context_docs = context_docs or []

    # Run DeepEval in thread pool (it's sync and slow)
    loop = asyncio.get_event_loop()
    deepeval_scores = await loop.run_in_executor(
        _executor, _run_deepeval, query, response, context_docs
    )

    # LLM judge (reuse graph evaluator node inline)
    judge_scores: dict = {}
    try:
        from app.agents._common import llm_json_call

        judge_prompt = f"""You are a supply chain expert judge.

Query: {query}
Response: {response[:1500]}

Rate the response:
{{
  "scores": {{"feasibility": 0-10, "specificity": 0-10, "impact": 0-10, "timeline_realism": 0-10}},
  "overall_score": 0-10,
  "verdict": "APPROVED|NEEDS_REVISION|REJECTED",
  "reasoning": "..."
}}"""
        judge_result, _ = await llm_json_call(
            "You are an expert supply chain risk management judge. Return only valid JSON.",
            judge_prompt,
        )
        judge_scores = judge_result
    except Exception as exc:
        logger.warning("LLM judge failed: %s", exc)

    # Persist evaluation result
    verdict_str = judge_scores.get("verdict", "NEEDS_REVISION")
    verdict_enum = None
    try:
        verdict_enum = JudgeVerdict(verdict_str)
    except ValueError:
        pass

    scores_dict = judge_scores.get("scores", {})
    eval_record = EvaluationResult(
        id=str(uuid.uuid4()),
        session_id=req.session_id,
        answer_relevancy=deepeval_scores.get("answer_relevancy"),
        faithfulness=deepeval_scores.get("faithfulness"),
        contextual_recall=deepeval_scores.get("contextual_recall"),
        contextual_precision=deepeval_scores.get("contextual_precision"),
        judge_feasibility=scores_dict.get("feasibility"),
        judge_specificity=scores_dict.get("specificity"),
        judge_impact=scores_dict.get("impact"),
        judge_timeline_realism=scores_dict.get("timeline_realism"),
        judge_overall=judge_scores.get("overall_score"),
        judge_verdict=verdict_enum,
        judge_reasoning=judge_scores.get("reasoning"),
    )
    db.add(eval_record)
    await db.commit()
    await db.refresh(eval_record)

    return ok(EvaluationResultResponse.model_validate(eval_record).model_dump())


@router.get("/results")
async def list_evaluation_results(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EvaluationResult)
        .order_by(EvaluationResult.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    records = result.scalars().all()
    return ok(
        [EvaluationResultResponse.model_validate(r).model_dump() for r in records],
        meta={"skip": skip, "limit": limit},
    )


@router.get("/results/{result_id}")
async def get_evaluation_result(
    result_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EvaluationResult).where(EvaluationResult.id == result_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Evaluation result not found.")
    return ok(EvaluationResultResponse.model_validate(record).model_dump())
