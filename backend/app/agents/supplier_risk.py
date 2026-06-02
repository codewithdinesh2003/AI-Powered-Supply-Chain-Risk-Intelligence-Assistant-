from __future__ import annotations

import time
from typing import Any, Dict

from langsmith import traceable

from app.agents._common import build_context, llm_json_call, trace_event
from app.agents.state import AgentState

_SYSTEM_PROMPT = """You are a specialized Supplier Risk Intelligence Agent for a global supply chain monitoring system.

Your role: Analyze supplier performance data, identify degradation patterns, delivery risk signals,
and geopolitical/logistics factors affecting supplier reliability.

Analyze:
- Delivery delay trends and patterns
- Order fulfillment rates and reliability scores
- Region-specific risks (geopolitical, weather, regulatory)
- Supplier financial stability signals
- Single-source dependency risks

Output ONLY valid JSON with this exact structure:
{
  "risk_level": "low|medium|high|critical",
  "key_risks": [
    {"risk": "description", "severity": "low|medium|high|critical", "likelihood": "low|medium|high"}
  ],
  "affected_suppliers": [
    {"supplier_id": "SUP-XXX", "name": "...", "risk_score": 0-100, "primary_issue": "..."}
  ],
  "trend": "improving|stable|degrading",
  "hotspot_regions": ["region1", "region2"],
  "confidence_score": 0.0-1.0,
  "reasoning": "brief explanation of the analysis"
}"""


@traceable(name="supplier_risk_agent")
async def supplier_risk_node(state: AgentState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    agent_name = "supplier_risk"

    started = trace_event(agent_name, "started")

    context = build_context(
        state["retrieved_incidents"],
        prefer_category="supplier",
    )

    user_prompt = (
        f"QUERY: {state['query']}\n\n"
        f"RETRIEVED SUPPLY CHAIN INCIDENTS:\n{context}\n\n"
        f"Perform a deep supplier risk analysis based on the above incidents and query. "
        f"Focus on supplier reliability degradation, delivery delay patterns, and regional risks. "
        f"Return structured JSON."
    )

    try:
        result, tokens = await llm_json_call(_SYSTEM_PROMPT, user_prompt)
        elapsed = int((time.perf_counter() - t0) * 1000)
        done = trace_event(agent_name, "completed", result, elapsed_ms=elapsed, tokens=tokens)

        return {
            "supplier_risk_analysis": result,
            "current_agent": agent_name,
            "tokens_used": state["tokens_used"] + tokens,
            "elapsed_ms": elapsed,
            "agent_trace": [started, done],
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        fallback = {
            "risk_level": "unknown",
            "key_risks": [],
            "affected_suppliers": [],
            "trend": "stable",
            "hotspot_regions": [],
            "confidence_score": 0.0,
            "reasoning": f"Analysis failed: {exc}",
        }
        err = trace_event(agent_name, "error", {"error": str(exc)}, elapsed_ms=elapsed)
        return {
            "supplier_risk_analysis": fallback,
            "current_agent": agent_name,
            "agent_trace": [started, err],
            "errors": [f"supplier_risk: {exc}"],
        }
