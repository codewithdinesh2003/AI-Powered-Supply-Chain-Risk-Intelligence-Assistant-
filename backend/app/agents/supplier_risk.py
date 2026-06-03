from __future__ import annotations

import time
from typing import Any, Dict

from langsmith import traceable

from app.agents._common import build_context, llm_json_call, trace_event
from app.agents.state import AgentState

_SYSTEM_PROMPT = """You are a Supplier Risk Intelligence Agent. Identify the top supplier risks.

BE CONCISE — total JSON response must be under 400 tokens.
Limit key_risks and affected_suppliers to TOP 2 each.

Output ONLY valid JSON:
{
  "risk_level": "critical|high|medium|low",
  "key_risks": [{"risk": "...", "severity": "critical|high|medium|low"}],
  "affected_suppliers": [{"supplier_id": "...", "name": "...", "risk_score": 0, "primary_issue": "..."}],
  "trend": "degrading|stable|improving",
  "hotspot_regions": ["region"],
  "confidence_score": 0.85,
  "reasoning": "one sentence"
}"""


@traceable(name="supplier_risk_agent")
async def supplier_risk_node(state: AgentState) -> Dict[str, Any]:
    t0 = time.perf_counter()
    agent_name = "supplier_risk"
    n_chunks = len(state.get("retrieved_incidents", []))

    events = [
        trace_event(agent_name, "started", {"message": f"Received {n_chunks} context chunks"}),
        trace_event(agent_name, "log",     {"message": "Scanning supplier delivery patterns and reliability scores", "log_type": "info"}),
    ]

    context = build_context(state["retrieved_incidents"], prefer_category="supplier")

    events.append(trace_event(agent_name, "log", {"message": "Checking regional risk factors and geopolitical signals", "log_type": "info"}))

    user_prompt = (
        f"QUERY: {state['query']}\n\n"
        f"RETRIEVED SUPPLY CHAIN INCIDENTS:\n{context}\n\n"
        f"Perform a deep supplier risk analysis. Focus on supplier reliability degradation, "
        f"delivery delay patterns, and regional risks. Return structured JSON."
    )

    try:
        result, tokens = await llm_json_call(_SYSTEM_PROMPT, user_prompt)
        elapsed = int((time.perf_counter() - t0) * 1000)

        risk_level   = result.get("risk_level", "unknown")
        n_affected   = len(result.get("affected_suppliers", []))
        n_risks      = len(result.get("key_risks", []))
        log_type     = "warn" if risk_level in ("high", "critical") else "info"

        events.append(trace_event(agent_name, "log", {
            "message": f"Identified {n_risks} key risks across {n_affected} suppliers",
            "log_type": log_type,
        }))
        events.append(trace_event(agent_name, "completed", {
            "message": f"Risk: {risk_level.upper()} — {n_affected} suppliers flagged",
            "tokens_used": tokens,
            "elapsed_ms": elapsed,
        }))

        return {
            "supplier_risk_analysis": result,
            "current_agent": agent_name,
            "tokens_used": state["tokens_used"] + tokens,
            "elapsed_ms": elapsed,
            "agent_trace": events,
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        fallback = {
            "risk_level": "unknown", "key_risks": [], "affected_suppliers": [],
            "trend": "stable", "hotspot_regions": [], "confidence_score": 0.0,
            "reasoning": f"Analysis failed: {exc}",
        }
        events.append(trace_event(agent_name, "error", {"error": str(exc), "message": str(exc)}, elapsed_ms=elapsed))
        return {
            "supplier_risk_analysis": fallback,
            "current_agent": agent_name,
            "agent_trace": events,
            "errors": [f"supplier_risk: {exc}"],
        }
