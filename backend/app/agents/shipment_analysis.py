from __future__ import annotations

import time
from typing import Any, Dict

from langsmith import traceable

from app.agents._common import build_context, llm_json_call, trace_event
from app.agents.state import AgentState

_SYSTEM_PROMPT = """You are a Shipment Delay Prediction Agent. Predict delays and logistics risks.

BE CONCISE — total JSON response must be under 400 tokens.
Limit affected_routes and disruption_hotspots to TOP 2 each.

Output ONLY valid JSON:
{
  "delay_probability": 0.75,
  "estimated_delay_days": 5.0,
  "affected_routes": [{"route": "A→B", "congestion_level": "high", "avg_delay_days": 5.0}],
  "cost_impact": {"estimated_additional_cost_usd": 10000, "cost_increase_pct": 20.0, "primary_cost_driver": "..."},
  "disruption_hotspots": [{"location": "...", "issue_type": "...", "severity": "high"}],
  "recommended_actions": ["action"],
  "confidence_score": 0.85,
  "reasoning": "one sentence"
}"""


@traceable(name="shipment_analysis_agent")
async def shipment_analysis_node(state: AgentState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    agent_name = "shipment_analysis"
    n_chunks = len(state.get("retrieved_incidents", []))

    events = [
        trace_event(agent_name, "started", {"message": f"Received {n_chunks} context chunks"}),
        trace_event(agent_name, "log",     {"message": "Analyzing route congestion indicators and port status", "log_type": "info"}),
    ]

    context = build_context(state["retrieved_incidents"], prefer_category="shipment")

    events.append(trace_event(agent_name, "log", {"message": "Computing delay probability model from historical patterns", "log_type": "info"}))

    user_prompt = (
        f"QUERY: {state['query']}\n\n"
        f"RETRIEVED SUPPLY CHAIN INCIDENTS:\n{context}\n\n"
        f"Analyze shipment delays, port congestion, transportation cost spikes, "
        f"and logistics bottlenecks. Predict delay probability and quantify cost impact. Return structured JSON."
    )

    try:
        result, tokens = await llm_json_call(_SYSTEM_PROMPT, user_prompt)
        elapsed = int((time.perf_counter() - t0) * 1000)

        delay_prob   = result.get("delay_probability", 0)
        delay_days   = result.get("estimated_delay_days", 0)
        n_hotspots   = len(result.get("disruption_hotspots", []))
        log_type     = "warn" if delay_prob > 0.5 else "info"

        events.append(trace_event(agent_name, "log", {
            "message": f"{n_hotspots} disruption hotspots detected — est. {delay_days:.1f}d delay",
            "log_type": log_type,
        }))
        events.append(trace_event(agent_name, "completed", {
            "message": f"Delay probability: {delay_prob:.0%} — estimated {delay_days:.1f} day delay",
            "tokens_used": tokens,
            "elapsed_ms": elapsed,
        }))

        return {
            "shipment_analysis": result,
            "current_agent": agent_name,
            "tokens_used": state["tokens_used"] + tokens,
            "elapsed_ms": elapsed,
            "agent_trace": events,
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        fallback = {
            "delay_probability": 0.0, "estimated_delay_days": 0.0,
            "affected_routes": [], "cost_impact": {"estimated_additional_cost_usd": 0, "cost_increase_pct": 0.0, "primary_cost_driver": "unknown"},
            "disruption_hotspots": [], "recommended_actions": [], "confidence_score": 0.0,
            "reasoning": f"Analysis failed: {exc}",
        }
        events.append(trace_event(agent_name, "error", {"error": str(exc), "message": str(exc)}, elapsed_ms=elapsed))
        return {
            "shipment_analysis": fallback,
            "current_agent": agent_name,
            "agent_trace": events,
            "errors": [f"shipment_analysis: {exc}"],
        }
