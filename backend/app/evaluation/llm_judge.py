"""LLM-as-judge for supply chain mitigation recommendation quality.

Uses GPT-4o to rate each recommendation on four supply-chain-specific
dimensions and returns a structured verdict with improvement suggestions.

Scoring dimensions (0–10 each):
  feasibility       — can the action be implemented given real-world constraints?
  specificity       — is it actionable (names suppliers / routes / SKUs) vs generic?
  impact            — will it meaningfully reduce risk?
  timeline_realism  — is the timeframe achievable?

Verdict mapping:
  overall ≥ 7.5 → APPROVED
  overall ≥ 5.0 → NEEDS_REVISION
  overall <  5.0 → REJECTED
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agents._common import llm_json_call

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class JudgmentResult:
    feasibility: float = 0.0
    specificity: float = 0.0
    impact: float = 0.0
    timeline_realism: float = 0.0
    overall_score: float = 0.0
    verdict: str = "NEEDS_REVISION"         # APPROVED | NEEDS_REVISION | REJECTED
    reasoning: str = ""
    improvement_suggestions: List[str] = field(default_factory=list)
    tokens_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scores": {
                "feasibility": self.feasibility,
                "specificity": self.specificity,
                "impact": self.impact,
                "timeline_realism": self.timeline_realism,
            },
            "overall_score": self.overall_score,
            "verdict": self.verdict,
            "reasoning": self.reasoning,
            "improvement_suggestions": self.improvement_suggestions,
            "tokens_used": self.tokens_used,
        }


# ── Prompt ────────────────────────────────────────────────────────────────────

_JUDGE_SYSTEM_PROMPT = """You are a senior supply chain risk management expert and independent evaluator.

Your task is to rigorously assess the quality of AI-generated mitigation recommendations
for supply chain disruptions.

Scoring guide (0–10 for each dimension):
- feasibility       (0=impossible, 5=possible with effort, 10=easy to implement immediately)
- specificity       (0=vague platitudes, 5=partially specific, 10=names exact suppliers/routes/SKUs/quantities)
- impact            (0=no effect, 5=moderate risk reduction, 10=eliminates the root cause)
- timeline_realism  (0=fantasy timeline, 5=tight but possible, 10=comfortably achievable)

Verdict rules:
  APPROVED       — overall_score ≥ 7.5  (ready to execute as-is)
  NEEDS_REVISION — overall_score ≥ 5.0  (good direction but needs detail or adjustment)
  REJECTED       — overall_score < 5.0  (fundamentally flawed or unsafe)

Return ONLY valid JSON matching this exact schema:
{
  "scores": {
    "feasibility": 0.0,
    "specificity": 0.0,
    "impact": 0.0,
    "timeline_realism": 0.0
  },
  "overall_score": 0.0,
  "verdict": "APPROVED|NEEDS_REVISION|REJECTED",
  "reasoning": "2–3 sentence explanation referencing specific strengths and weaknesses",
  "improvement_suggestions": ["specific suggestion 1", "specific suggestion 2"]
}"""


# ── Core judge function ───────────────────────────────────────────────────────

async def judge_mitigation(
    recommendation: str,
    context: str,
    query: str,
    *,
    recommendation_id: Optional[str] = None,
) -> JudgmentResult:
    """Evaluate a single mitigation recommendation with GPT-4o as judge.

    Parameters
    ----------
    recommendation: The recommendation text or JSON string.
    context:        Relevant supply chain context (retrieved incident texts).
    query:          The original user query that triggered the recommendation.
    recommendation_id: Optional label for logging.
    """
    label = recommendation_id or "recommendation"

    user_prompt = (
        f"SUPPLY CHAIN QUERY:\n{query}\n\n"
        f"SUPPLY CHAIN CONTEXT (retrieved incidents):\n"
        f"{context[:3000]}\n\n"
        f"MITIGATION RECOMMENDATION TO EVALUATE:\n"
        f"{recommendation[:2000]}\n\n"
        f"Evaluate this recommendation according to the four dimensions. "
        f"Be strict — P1 recommendations must be immediately actionable. "
        f"Return structured JSON."
    )

    try:
        raw, tokens = await llm_json_call(_JUDGE_SYSTEM_PROMPT, user_prompt)

        scores = raw.get("scores", {})
        f_score   = float(scores.get("feasibility",      raw.get("feasibility",      5.0)))
        s_score   = float(scores.get("specificity",      raw.get("specificity",      5.0)))
        i_score   = float(scores.get("impact",           raw.get("impact",           5.0)))
        t_score   = float(scores.get("timeline_realism", raw.get("timeline_realism", 5.0)))
        overall   = float(raw.get("overall_score", (f_score + s_score + i_score + t_score) / 4))

        # Enforce verdict from overall_score if model gives inconsistent value
        if overall >= 7.5:
            verdict = "APPROVED"
        elif overall >= 5.0:
            verdict = "NEEDS_REVISION"
        else:
            verdict = "REJECTED"

        result = JudgmentResult(
            feasibility=round(f_score, 2),
            specificity=round(s_score, 2),
            impact=round(i_score, 2),
            timeline_realism=round(t_score, 2),
            overall_score=round(overall, 2),
            verdict=verdict,
            reasoning=raw.get("reasoning", ""),
            improvement_suggestions=raw.get("improvement_suggestions", []),
            tokens_used=tokens,
        )
        logger.info(
            "Judge [%s] verdict=%s overall=%.1f",
            label, result.verdict, result.overall_score,
        )
        return result

    except Exception as exc:
        logger.error("LLM judge failed for %s: %s", label, exc, exc_info=True)
        return JudgmentResult(
            overall_score=0.0,
            verdict="NEEDS_REVISION",
            reasoning=f"Judge evaluation failed: {exc}",
        )


async def judge_all_recommendations(
    recommendations: List[Dict[str, Any]],
    context: str,
    query: str,
) -> List[Dict[str, Any]]:
    """Judge every recommendation in a list and attach verdict to each.

    Returns the input list enriched with a ``judgment`` key per item.
    """
    import asyncio

    async def _judge_one(rec: Dict[str, Any]) -> Dict[str, Any]:
        rec_text = (
            f"Priority: {rec.get('priority', 'N/A')}\n"
            f"Action: {rec.get('action', '')}\n"
            f"Rationale: {rec.get('rationale', '')}\n"
            f"Timeline: {rec.get('timeline', '')}\n"
            f"Expected Impact: {rec.get('expected_impact', '')}\n"
            f"Responsible Team: {rec.get('responsible_team', '')}"
        )
        judgment = await judge_mitigation(
            recommendation=rec_text,
            context=context,
            query=query,
            recommendation_id=rec.get("id", "?"),
        )
        return {**rec, "judgment": judgment.to_dict()}

    return await asyncio.gather(*[_judge_one(r) for r in recommendations])
