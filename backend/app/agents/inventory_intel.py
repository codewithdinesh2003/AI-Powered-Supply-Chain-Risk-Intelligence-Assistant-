from __future__ import annotations

import time
from typing import Any, Dict

from langsmith import traceable

from app.agents._common import build_context, llm_json_call, trace_event
from app.agents.state import AgentState

_SYSTEM_PROMPT = """You are an Inventory Intelligence Agent specializing in stockout prediction and demand-supply analysis.

Your role: Detect inventory risks, predict stockouts, and identify demand-supply imbalances.

Analyze:
- Current inventory levels versus demand forecasts
- Reorder point breaches and safety stock erosion
- Warehouse capacity constraints and location imbalances
- Demand spike patterns (seasonal, promotional, external events)
- Lead time variability and its impact on inventory planning
- Coverage ratio trends (inventory / demand)

Output ONLY valid JSON with this exact structure:
{
  "stockout_risk_items": [
    {
      "item": "...",
      "supplier_id": "SUP-XXX",
      "current_inventory": 0,
      "demand_forecast": 0,
      "coverage_ratio": 0.0,
      "days_until_stockout": 0,
      "risk_level": "low|medium|high|critical"
    }
  ],
  "demand_surge_detected": true|false,
  "demand_surge_details": {"magnitude_pct": 0.0, "affected_categories": [], "likely_cause": "..."},
  "reorder_recommendations": [
    {"supplier_id": "SUP-XXX", "item": "...", "recommended_order_qty": 0, "urgency": "immediate|soon|planned"}
  ],
  "warehouse_imbalances": [
    {"location": "...", "issue": "overstocked|understocked", "severity": "low|medium|high"}
  ],
  "overall_inventory_health": "critical|at_risk|adequate|healthy",
  "confidence_score": 0.0-1.0,
  "reasoning": "brief explanation"
}"""


@traceable(name="inventory_intel_agent")
async def inventory_intel_node(state: AgentState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    agent_name = "inventory_intel"

    started = trace_event(agent_name, "started")

    context = build_context(
        state["retrieved_incidents"],
        prefer_category="inventory",
    )

    user_prompt = (
        f"QUERY: {state['query']}\n\n"
        f"RETRIEVED SUPPLY CHAIN INCIDENTS:\n{context}\n\n"
        f"Analyze inventory levels, demand forecasts, stockout risks, and demand-supply imbalances "
        f"based on the incidents above. Identify items at risk of stockout and recommend reorder actions. "
        f"Return structured JSON."
    )

    try:
        result, tokens = await llm_json_call(_SYSTEM_PROMPT, user_prompt)
        elapsed = int((time.perf_counter() - t0) * 1000)
        done = trace_event(agent_name, "completed", result, elapsed_ms=elapsed, tokens=tokens)

        return {
            "inventory_analysis": result,
            "current_agent": agent_name,
            "tokens_used": state["tokens_used"] + tokens,
            "elapsed_ms": elapsed,
            "agent_trace": [started, done],
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        fallback = {
            "stockout_risk_items": [],
            "demand_surge_detected": False,
            "demand_surge_details": {},
            "reorder_recommendations": [],
            "warehouse_imbalances": [],
            "overall_inventory_health": "unknown",
            "confidence_score": 0.0,
            "reasoning": f"Analysis failed: {exc}",
        }
        err = trace_event(agent_name, "error", {"error": str(exc)}, elapsed_ms=elapsed)
        return {
            "inventory_analysis": fallback,
            "current_agent": agent_name,
            "agent_trace": [started, err],
            "errors": [f"inventory_intel: {exc}"],
        }
