"""DeepEval-based quality evaluation for supply chain RAG responses.

Runs four RAG metrics:
  - AnswerRelevancy    — is the answer relevant to the query?
  - Faithfulness       — does the answer stay faithful to the retrieved context?
  - ContextualRecall   — does the context cover the ground truth?
  - ContextualPrecision— are retrieved docs actually relevant (no noise)?

DeepEval metrics are synchronous; this module wraps them in asyncio's thread
pool so they don't block the event loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="deepeval")


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    answer_relevancy: Optional[float] = None
    faithfulness: Optional[float] = None
    contextual_recall: Optional[float] = None
    contextual_precision: Optional[float] = None
    passed: bool = False
    errors: List[str] = field(default_factory=list)

    @property
    def average_score(self) -> Optional[float]:
        scores = [s for s in [
            self.answer_relevancy,
            self.faithfulness,
            self.contextual_recall,
            self.contextual_precision,
        ] if s is not None]
        return round(sum(scores) / len(scores), 4) if scores else None

    def to_dict(self) -> Dict[str, object]:
        return {
            "answer_relevancy": self.answer_relevancy,
            "faithfulness": self.faithfulness,
            "contextual_recall": self.contextual_recall,
            "contextual_precision": self.contextual_precision,
            "average_score": self.average_score,
            "passed": self.passed,
            "errors": self.errors,
        }


# ── Core synchronous runner (called in thread pool) ───────────────────────────

def _run_metrics_sync(
    query: str,
    response: str,
    context: List[str],
    model: str,
) -> EvalResult:
    """Execute DeepEval metrics synchronously inside a worker thread."""
    # Ensure OpenAI key is visible in the thread's environment
    settings = get_settings()
    os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)

    result = EvalResult()

    try:
        from deepeval.metrics import (
            AnswerRelevancyMetric,
            ContextualPrecisionMetric,
            ContextualRecallMetric,
            FaithfulnessMetric,
        )
        from deepeval.test_case import LLMTestCase

        test_case = LLMTestCase(
            input=query,
            actual_output=response,
            retrieval_context=context[:5],  # cap to 5 docs for cost control
        )

        metric_specs = [
            ("answer_relevancy",    AnswerRelevancyMetric(threshold=0.7,    model=model, async_mode=False)),
            ("faithfulness",        FaithfulnessMetric(threshold=0.8,       model=model, async_mode=False)),
            ("contextual_recall",   ContextualRecallMetric(threshold=0.7,   model=model, async_mode=False)),
            ("contextual_precision",ContextualPrecisionMetric(threshold=0.7,model=model, async_mode=False)),
        ]

        for attr, metric in metric_specs:
            try:
                metric.measure(test_case)
                setattr(result, attr, round(float(metric.score), 4))
            except Exception as exc:
                logger.warning("Metric %s failed: %s", attr, exc)
                result.errors.append(f"{attr}: {exc}")

        # Passed if all measured scores meet their thresholds
        thresholds = {"answer_relevancy": 0.7, "faithfulness": 0.8,
                      "contextual_recall": 0.7, "contextual_precision": 0.7}
        result.passed = all(
            (getattr(result, attr) or 0) >= thresh
            for attr, thresh in thresholds.items()
            if getattr(result, attr) is not None
        )

    except ImportError as exc:
        msg = f"DeepEval not installed or import error: {exc}"
        logger.error(msg)
        result.errors.append(msg)
    except Exception as exc:
        msg = f"Evaluation run failed: {exc}"
        logger.error(msg, exc_info=True)
        result.errors.append(msg)

    return result


# ── Public async interface ────────────────────────────────────────────────────

class SupplyChainEvaluator:
    """Async wrapper around DeepEval metrics for supply chain RAG quality."""

    def __init__(self, model: str = "gpt-4o") -> None:
        self._model = model

    async def evaluate(
        self,
        query: str,
        response: str,
        context: List[str],
    ) -> EvalResult:
        """Run all four RAG metrics asynchronously (offloaded to thread pool).

        Parameters
        ----------
        query:    The original user question.
        response: The final LLM-generated answer / executive summary.
        context:  List of retrieved document texts used as grounding.
        """
        if not response or not query:
            return EvalResult(errors=["Empty query or response — skipping evaluation."])

        loop = asyncio.get_event_loop()
        result: EvalResult = await loop.run_in_executor(
            _executor,
            _run_metrics_sync,
            query,
            response,
            context,
            self._model,
        )
        logger.info(
            "DeepEval complete — avg score: %s, passed: %s, errors: %d",
            result.average_score,
            result.passed,
            len(result.errors),
        )
        return result

    async def evaluate_batch(
        self,
        cases: List[Dict[str, object]],
    ) -> List[EvalResult]:
        """Evaluate a batch of (query, response, context) dicts concurrently."""
        tasks = [
            self.evaluate(
                query=str(c.get("query", "")),
                response=str(c.get("response", "")),
                context=list(c.get("context", [])),
            )
            for c in cases
        ]
        return await asyncio.gather(*tasks)


# ── Module-level convenience function ────────────────────────────────────────

_default_evaluator: Optional[SupplyChainEvaluator] = None


def get_evaluator() -> SupplyChainEvaluator:
    global _default_evaluator
    if _default_evaluator is None:
        _default_evaluator = SupplyChainEvaluator()
    return _default_evaluator


async def evaluate_response(
    query: str,
    response: str,
    context: List[str],
) -> EvalResult:
    """Shortcut — evaluate using the module-level default evaluator."""
    return await get_evaluator().evaluate(query, response, context)
