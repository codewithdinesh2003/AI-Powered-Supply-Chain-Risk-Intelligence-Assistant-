from __future__ import annotations

import time
from typing import Any, Dict

from langsmith import traceable

from app.agents._common import build_context, llm_json_call, trace_event
from app.agents.state import AgentState

_SYSTEM_PROMPT = """You are an Inventory Intelligence Agent. Detect stockout risks and demand-supply imbalances.

BE CONCISE — total JSON response must be under 400 tokens.
Limit stockout_risk_items to the TOP 2 most critical items only.

Output ONLY valid JSON:
{
  "stockout_risk_items": [
    {"item": "...", "supplier_id": "...", "current_inventory": 0, "demand_forecast": 0, "coverage_ratio": 0.0, "days_until_stockout": 0, "risk_level": "critical|high|medium|low"}
  ],
  "demand_surge_detected": true,
  "reorder_recommendations": [{"supplier_id": "...", "item": "...", "urgency": "immediate|soon|planned"}],
  "overall_inventory_health": "critical|at_risk|adequate|healthy",
  "confidence_score": 0.85,
  "reasoning": "one sentence"
}"""


@traceable(name="inventory_intel_agent")
async def inventory_intel_node(state: AgentState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    agent_name = "inventory_intel"
    n_chunks = len(state.get("retrieved_incidents", []))

    events = [
        trace_event(agent_name, "started", {"message": f"Received {n_chunks} context chunks"}),
        trace_event(agent_name, "log",     {"message": "Checking stockout risk indicators and coverage ratios", "log_type": "info"}),
    ]

    context = build_context(state["retrieved_incidents"], prefer_category="inventory")

    events.append(trace_event(agent_name, "log", {"message": "Analyzing demand-supply balance and reorder points", "log_type": "info"}))

    user_prompt = (
        f"QUERY: {state['query']}\n\n"
        f"RETRIEVED SUPPLY CHAIN INCIDENTS:\n{context}\n\n"
        f"Analyze inventory levels, demand forecasts, stockout risks, and demand-supply imbalances. "
        f"Identify items at risk of stockout and recommend reorder actions. Return structured JSON."
    )

    try:
        result, tokens = await llm_json_call(_SYSTEM_PROMPT, user_prompt)
        elapsed = int((time.perf_counter() - t0) * 1000)

        n_stockout   = len(result.get("stockout_risk_items", []))
        surge        = result.get("demand_surge_detected", False)
        health       = result.get("overall_inventory_health", "unknown")
        log_type     = "warn" if n_stockout > 0 or surge else "info"

        events.append(trace_event(agent_name, "log", {
            "message": f"{n_stockout} items at stockout risk — demand surge: {'YES' if surge else 'no'}",
            "log_type": log_type,
        }))
        events.append(trace_event(agent_name, "completed", {
            "message": f"Inventory health: {health.upper()} — {n_stockout} items at risk",
            "tokens_used": tokens,
            "elapsed_ms": elapsed,
        }))

        return {
            "inventory_analysis": result,
            "current_agent": agent_name,
            "tokens_used": state["tokens_used"] + tokens,
            "elapsed_ms": elapsed,
            "agent_trace": events,
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        fallback = {
            "stockout_risk_items": [], "demand_surge_detected": False,
            "demand_surge_details": {}, "reorder_recommendations": [],
            "warehouse_imbalances": [], "overall_inventory_health": "unknown",
            "confidence_score": 0.0, "reasoning": f"Analysis failed: {exc}",
        }
        events.append(trace_event(agent_name, "error", {"error": str(exc), "message": str(exc)}, elapsed_ms=elapsed))
        return {
            "inventory_analysis": fallback,
            "current_agent": agent_name,
            "agent_trace": events,
            "errors": [f"inventory_intel: {exc}"],
        }
