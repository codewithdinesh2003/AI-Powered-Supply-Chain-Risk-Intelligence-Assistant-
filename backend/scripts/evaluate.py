#!/usr/bin/env python
"""Run the full DeepEval + LLM-judge evaluation suite against stored query sessions.

Usage:
    python scripts/evaluate.py                  # evaluate last 20 sessions
    python scripts/evaluate.py --limit 50       # evaluate last 50 sessions
    python scripts/evaluate.py --session-id <id>  # evaluate one specific session
    python scripts/evaluate.py --export results.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from sqlalchemy import select

from app.database.connection import get_db_session, init_db
from app.database.models import EvaluationResult, JudgeVerdict, QuerySession
from app.evaluation.deepeval_metrics import SupplyChainEvaluator
from app.evaluation.llm_judge import judge_all_recommendations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def evaluate_session(
    session: QuerySession,
    evaluator: SupplyChainEvaluator,
) -> dict:
    """Run DeepEval + LLM judge for a single query session."""
    result_data   = session.result or {}
    retrieval_ctx = session.retrieval_context or {}

    query    = session.query_text
    response = result_data.get("final_response") or ""
    context  = [d.get("text", "") for d in retrieval_ctx.get("documents", [])][:5]
    recs     = result_data.get("recommendations", [])

    logger.info("Evaluating session %s: '%s'", session.session_id, query[:60])

    # ── DeepEval RAG metrics ──────────────────────────────────────────────
    eval_result = await evaluator.evaluate(query=query, response=response, context=context)

    # ── LLM judge for recommendations ────────────────────────────────────
    judge_results: list = []
    if recs:
        ctx_text = "\n\n".join(context[:3])
        try:
            judge_results = await judge_all_recommendations(recs, ctx_text, query)
        except Exception as exc:
            logger.warning("Judge failed for %s: %s", session.session_id, exc)

    # Overall judge verdict — use worst-case across recommendations
    overall_score  = None
    overall_verdict = None
    if judge_results:
        scores   = [r.get("judgment", {}).get("overall_score", 5.0) for r in judge_results]
        overall_score   = round(sum(scores) / len(scores), 2)
        verdicts = [r.get("judgment", {}).get("verdict", "NEEDS_REVISION") for r in judge_results]
        if "REJECTED" in verdicts:
            overall_verdict = JudgeVerdict.rejected
        elif "APPROVED" in verdicts and "NEEDS_REVISION" not in verdicts:
            overall_verdict = JudgeVerdict.approved
        else:
            overall_verdict = JudgeVerdict.needs_revision

    return {
        "session_id":           session.session_id,
        "query":                query[:100],
        "deepeval": {
            "answer_relevancy":    eval_result.answer_relevancy,
            "faithfulness":        eval_result.faithfulness,
            "contextual_recall":   eval_result.contextual_recall,
            "contextual_precision":eval_result.contextual_precision,
            "average_score":       eval_result.average_score,
            "passed":              eval_result.passed,
            "errors":              eval_result.errors,
        },
        "judge": {
            "overall_score": overall_score,
            "verdict":       overall_verdict.value if overall_verdict else None,
        },
        "eval_result": eval_result,
        "judge_verdict_enum": overall_verdict,
        "judge_overall_score": overall_score,
    }


async def persist_result(session: QuerySession, result: dict) -> None:
    """Write evaluation scores back to MySQL."""
    async with get_db_session() as db:
        import uuid
        rec = EvaluationResult(
            id=str(uuid.uuid4()),
            session_id=session.session_id,
            answer_relevancy=result["deepeval"]["answer_relevancy"],
            faithfulness=result["deepeval"]["faithfulness"],
            contextual_recall=result["deepeval"]["contextual_recall"],
            contextual_precision=result["deepeval"]["contextual_precision"],
            judge_overall=result["judge"]["overall_score"],
            judge_verdict=result["judge_verdict_enum"],
        )
        db.add(rec)

        # Update session evaluation_score
        session.evaluation_score = result["deepeval"]["average_score"]
        session.judge_verdict     = result["judge_verdict_enum"]
        db.add(session)


async def main(args: argparse.Namespace) -> None:
    await init_db()
    evaluator = SupplyChainEvaluator()
    all_results: list[dict] = []

    async with get_db_session() as db:
        if args.session_id:
            stmt = select(QuerySession).where(QuerySession.session_id == args.session_id)
        else:
            stmt = (
                select(QuerySession)
                .order_by(QuerySession.created_at.desc())
                .limit(args.limit)
            )
        rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        print("[WARN] No sessions found matching the criteria.")
        return

    print(f"\nEvaluating {len(rows)} session(s)…\n{'─' * 60}")

    for session in rows:
        try:
            result = await evaluate_session(session, evaluator)
            await persist_result(session, result)
            all_results.append(result)

            dv = result["deepeval"]
            jv = result["judge"]
            print(
                f"  {session.session_id[:12]}…  "
                f"avg={dv['average_score'] or 'N/A':.2f}  "
                f"verdict={jv['verdict'] or 'N/A':<15}  "
                f"passed={'✓' if dv['passed'] else '✗'}"
            )
        except Exception as exc:
            logger.error("Failed to evaluate %s: %s", session.session_id, exc)

    # Summary
    scores = [r["deepeval"]["average_score"] for r in all_results if r["deepeval"]["average_score"] is not None]
    print(f"\n{'─' * 60}")
    print(f"  Sessions evaluated : {len(all_results)}")
    print(f"  Average RAG score  : {sum(scores)/len(scores):.3f}" if scores else "  Average RAG score  : N/A")
    pass_rate = sum(1 for r in all_results if r["deepeval"]["passed"]) / max(len(all_results), 1)
    print(f"  Pass rate          : {pass_rate:.0%}")

    approved = sum(1 for r in all_results if r["judge"]["verdict"] == "APPROVED")
    print(f"  LLM Judge approved : {approved}/{len(all_results)}")
    print(f"{'─' * 60}\n")

    if args.export:
        export_data = [
            {k: v for k, v in r.items() if k not in ("eval_result", "judge_verdict_enum")}
            for r in all_results
        ]
        with open(args.export, "w") as f:
            json.dump(export_data, f, indent=2, default=str)
        print(f"Results exported to {args.export}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DeepEval + LLM-judge evaluation suite.")
    parser.add_argument("--limit",      type=int, default=20, help="Number of recent sessions to evaluate")
    parser.add_argument("--session-id", type=str, default=None, help="Evaluate a specific session by ID")
    parser.add_argument("--export",     type=str, default=None, help="Export results to JSON file")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
