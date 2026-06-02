from __future__ import annotations

import time
from typing import Any, Dict

from langsmith import traceable

from app.agents._common import build_context, llm_json_call, trace_event
from app.agents.state import AgentState

_SYSTEM_PROMPT = """You are a Shipment Delay Prediction and Analysis Agent for a global supply chain system.

Your role: Predict shipment delays, identify logistics bottlenecks, and quantify cost impacts.

Analyze:
- Port congestion indicators and historical patterns
- Transportation cost spikes and carrier capacity constraints
- Shipment status anomalies (Customs-Hold, Critical, Delayed)
- Route-specific bottlenecks and alternative routing options
- Seasonal and event-driven disruption patterns

Output ONLY valid JSON with this exact structure:
{
  "delay_probability": 0.0-1.0,
  "estimated_delay_days": 0.0,
  "affected_routes": [
    {"route": "origin → destination", "congestion_level": "low|medium|high|critical", "avg_delay_days": 0.0}
  ],
  "cost_impact": {
    "estimated_additional_cost_usd": 0,
    "cost_increase_pct": 0.0,
    "primary_cost_driver": "..."
  },
  "disruption_hotspots": [
    {"location": "...", "issue_type": "...", "severity": "low|medium|high|critical"}
  ],
  "recommended_actions": ["action1", "action2"],
  "confidence_score": 0.0-1.0,
  "reasoning": "brief explanation"
}"""


@traceable(name="shipment_analysis_agent")
async def shipment_analysis_node(state: AgentState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    agent_name = "shipment_analysis"

    started = trace_event(agent_name, "started")

    context = build_context(
        state["retrieved_incidents"],
        prefer_category="shipment",
    )

    user_prompt = (
        f"QUERY: {state['query']}\n\n"
        f"RETRIEVED SUPPLY CHAIN INCIDENTS:\n{context}\n\n"
        f"Analyze shipment delays, port congestion, transportation cost spikes, "
        f"and logistics bottlenecks based on the incidents above. "
        f"Predict delay probability and quantify cost impact. Return structured JSON."
    )

    try:
        result, tokens = await llm_json_call(_SYSTEM_PROMPT, user_prompt)
        elapsed = int((time.perf_counter() - t0) * 1000)
        done = trace_event(agent_name, "completed", result, elapsed_ms=elapsed, tokens=tokens)

        return {
            "shipment_analysis": result,
            "current_agent": agent_name,
            "tokens_used": state["tokens_used"] + tokens,
            "elapsed_ms": elapsed,
            "agent_trace": [started, done],
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        fallback = {
            "delay_probability": 0.0,
            "estimated_delay_days": 0.0,
            "affected_routes": [],
            "cost_impact": {"estimated_additional_cost_usd": 0, "cost_increase_pct": 0.0, "primary_cost_driver": "unknown"},
            "disruption_hotspots": [],
            "recommended_actions": [],
            "confidence_score": 0.0,
            "reasoning": f"Analysis failed: {exc}",
        }
        err = trace_event(agent_name, "error", {"error": str(exc)}, elapsed_ms=elapsed)
        return {
            "shipment_analysis": fallback,
            "current_agent": agent_name,
            "agent_trace": [started, err],
            "errors": [f"shipment_analysis: {exc}"],
        }
