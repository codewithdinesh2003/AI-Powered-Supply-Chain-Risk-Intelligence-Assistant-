from __future__ import annotations

import json
import time
from typing import Any, Dict

from langsmith import traceable

from app.agents._common import llm_json_call, trace_event
from app.agents.state import AgentState

_SYSTEM_PROMPT = """You are a Supply Chain Mitigation Agent.
Output ONLY valid JSON under 450 tokens total.
Generate exactly 3 recommendations.
Keep ALL text fields under 12 words each.

{
  "recommendations": [
    {"id":"REC-001","priority":"P1","action":"<12 words","rationale":"<12 words",
     "timeline":"48 hours","expected_impact":"<12 words","responsible_team":"Logistics"},
    {"id":"REC-002","priority":"P2","action":"<12 words","rationale":"<12 words",
     "timeline":"1 week","expected_impact":"<12 words","responsible_team":"Procurement"},
    {"id":"REC-003","priority":"P3","action":"<12 words","rationale":"<12 words",
     "timeline":"2 weeks","expected_impact":"<12 words","responsible_team":"Operations"}
  ],
  "overall_risk_score": 75,
  "executive_summary": "<20 words for management",
  "confidence_score": 0.85
}"""


def _summarise(analysis: Any, label: str) -> str:
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

    events = [
        trace_event(agent_name, "started", {"message": "Consolidating 3 risk analyses"}),
        trace_event(agent_name, "log",     {"message": "Computing composite risk score across all domains", "log_type": "info"}),
    ]

    user_prompt = (
        f"ORIGINAL QUERY: {state['query']}\n\n"
        f"{_summarise(state.get('supplier_risk_analysis'),  'SUPPLIER RISK ANALYSIS')}\n"
        f"{_summarise(state.get('shipment_analysis'),       'SHIPMENT ANALYSIS')}\n"
        f"{_summarise(state.get('inventory_analysis'),      'INVENTORY ANALYSIS')}\n"
        f"Generate prioritized mitigation recommendations. Ensure recommendations are cross-functional "
        f"and address root causes. Return structured JSON."
    )

    events.append(trace_event(agent_name, "log", {"message": "Generating prioritized mitigation strategies", "log_type": "info"}))

    try:
        result, tokens = await llm_json_call(_SYSTEM_PROMPT, user_prompt)
        elapsed = int((time.perf_counter() - t0) * 1000)

        n_recs      = len(result.get("recommendations", []))
        risk_score  = float(result.get("overall_risk_score", 50))
        p1_count    = sum(1 for r in result.get("recommendations", []) if r.get("priority") == "P1")
        log_type    = "warn" if p1_count > 0 else "success"

        events.append(trace_event(agent_name, "log", {
            "message": f"{n_recs} recommendations generated — {p1_count} P1 critical actions",
            "log_type": log_type,
        }))
        events.append(trace_event(agent_name, "completed", {
            "message": f"{n_recs} recommendations (risk score: {risk_score:.0f}/100)",
            "tokens_used": tokens,
            "elapsed_ms": elapsed,
        }))

        return {
            "recommendations": result.get("recommendations", []),
            "final_response":  result.get("executive_summary", ""),
            "risk_score":      risk_score,
            "current_agent":   agent_name,
            "tokens_used":     state["tokens_used"] + tokens,
            "elapsed_ms":      elapsed,
            "agent_trace":     events,
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        events.append(trace_event(agent_name, "error", {"error": str(exc), "message": str(exc)}, elapsed_ms=elapsed))
        return {
            "recommendations": [],
            "final_response":  f"Recommendation generation failed: {exc}",
            "risk_score":      None,
            "current_agent":   agent_name,
            "agent_trace":     events,
            "errors":          [f"recommendation: {exc}"],
        }
