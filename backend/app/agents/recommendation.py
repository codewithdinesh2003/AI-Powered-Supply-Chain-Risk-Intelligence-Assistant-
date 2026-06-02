from __future__ import annotations

import json
import time
from typing import Any, Dict

from langsmith import traceable

from app.agents._common import llm_json_call, trace_event
from app.agents.state import AgentState

_SYSTEM_PROMPT = """You are a Supply Chain Mitigation Recommendation Agent.

Your role: Synthesize risk analyses from Supplier, Shipment, and Inventory agents into
prioritized, concrete, actionable mitigation strategies.

Guidelines:
- P1 (Critical): Requires action within 24–48 hours. Existential risk to operations.
- P2 (High):     Requires action within 1–2 weeks. Significant operational impact.
- P3 (Medium):   Requires action within 30 days. Manageable but needs attention.
- Each recommendation must be SPECIFIC (name suppliers, routes, SKUs where possible).
- Timeline must be realistic and quantified.
- Expected impact must be measurable.

Output ONLY valid JSON with this exact structure:
{
  "recommendations": [
    {
      "id": "REC-001",
      "priority": "P1|P2|P3",
      "action": "Concise action title",
      "rationale": "Why this action is needed, referencing specific data points",
      "timeline": "e.g. Within 48 hours / By end of week / Within 30 days",
      "expected_impact": "Quantified benefit, e.g. reduce delay by X days, save $X",
      "responsible_team": "e.g. Procurement / Logistics / Inventory Planning",
      "affected_suppliers": ["SUP-XXX"],
      "risk_domains": ["supplier|shipment|inventory|demand"]
    }
  ],
  "overall_risk_score": 0-100,
  "risk_breakdown": {
    "supplier_risk": 0-100,
    "shipment_risk": 0-100,
    "inventory_risk": 0-100
  },
  "executive_summary": "2–3 sentence non-technical summary suitable for senior management",
  "immediate_actions_required": true|false,
  "confidence_score": 0.0-1.0
}"""


def _summarise_analysis(analysis: Any, label: str) -> str:
    if not analysis:
        return f"{label}: No data available.\n"
    try:
        return f"{label}:\n{json.dumps(analysis, indent=2)}\n"
    except Exception:
        return f"{label}: {str(analysis)[:500]}\n"


@traceable(name="recommendation_agent")
async def recommendation_node(state: AgentState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    agent_name = "recommendation"

    started = trace_event(agent_name, "started")

    user_prompt = (
        f"ORIGINAL QUERY: {state['query']}\n\n"
        f"{_summarise_analysis(state.get('supplier_risk_analysis'), 'SUPPLIER RISK ANALYSIS')}\n"
        f"{_summarise_analysis(state.get('shipment_analysis'), 'SHIPMENT ANALYSIS')}\n"
        f"{_summarise_analysis(state.get('inventory_analysis'), 'INVENTORY ANALYSIS')}\n"
        f"Based on all three analyses above, generate a prioritized set of mitigation recommendations. "
        f"Ensure recommendations are cross-functional and address root causes, not just symptoms. "
        f"Return structured JSON."
    )

    try:
        result, tokens = await llm_json_call(_SYSTEM_PROMPT, user_prompt)
        elapsed = int((time.perf_counter() - t0) * 1000)
        done = trace_event(agent_name, "completed", result, elapsed_ms=elapsed, tokens=tokens)

        recommendations = result.get("recommendations", [])
        risk_score = float(result.get("overall_risk_score", 50.0))
        final_response = result.get("executive_summary", "")

        return {
            "recommendations": recommendations,
            "final_response": final_response,
            "risk_score": risk_score,
            "current_agent": agent_name,
            "tokens_used": state["tokens_used"] + tokens,
            "elapsed_ms": elapsed,
            "agent_trace": [started, done],
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        err = trace_event(agent_name, "error", {"error": str(exc)}, elapsed_ms=elapsed)
        return {
            "recommendations": [],
            "final_response": f"Recommendation generation failed: {exc}",
            "risk_score": None,
            "current_agent": agent_name,
            "agent_trace": [started, err],
            "errors": [f"recommendation: {exc}"],
        }
