"""LangGraph StateGraph — parallel agent execution with timeouts and context filtering."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from langsmith import traceable
from langgraph.graph import END, StateGraph

from app.agents._common import llm_json_call, trace_event
from app.agents.inventory_intel import inventory_intel_node
from app.agents.recommendation import recommendation_node
from app.agents.shipment_analysis import shipment_analysis_node
from app.agents.state import AgentState
from app.agents.supplier_risk import supplier_risk_node

logger = logging.getLogger(__name__)

_compiled_graph: Any = None

_AGENT_TIMEOUT = 25.0   # seconds per parallel agent
_PIPELINE_TIMEOUT = 90.0  # seconds total

# ── Context filtering — each agent sees only its most relevant chunks ─────────

_AGENT_LIMITS: Dict[str, int] = {
    "supplier_risk":     5,
    "shipment_analysis": 5,
    "inventory_intel":   4,
}
_AGENT_KEYWORDS: Dict[str, List[str]] = {
    "supplier_risk":     ["supplier", "defect", "vendor", "reliability", "quality"],
    "shipment_analysis": ["shipment", "route", "carrier", "transport", "port", "freight", "delay"],
    "inventory_intel":   ["inventory", "stock", "stockout", "demand", "warehouse", "reorder"],
}


def _filter_context(incidents: List[Dict[str, Any]], agent_name: str) -> List[Dict[str, Any]]:
    keywords = _AGENT_KEYWORDS.get(agent_name, [])
    limit    = _AGENT_LIMITS.get(agent_name, 5)
    if keywords:
        relevant = [
            i for i in incidents
            if any(k in i.get("text", "").lower() for k in keywords)
        ]
        if relevant:
            return relevant[:limit]
    return incidents[:limit]


# ── Per-agent timeout wrapper ─────────────────────────────────────────────────

async def _run_with_timeout(coro: Any, agent_name: str) -> Dict[str, Any]:
    try:
        return await asyncio.wait_for(coro, timeout=_AGENT_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("%s timed out after %.0fs", agent_name, _AGENT_TIMEOUT)
        t = trace_event(agent_name, "error", {
            "error":    f"Timed out after {_AGENT_TIMEOUT:.0f}s",
            "message":  f"Timed out after {_AGENT_TIMEOUT:.0f}s",
        })
        return {
            "agent_trace": [t],
            "errors":      [f"{agent_name}: timed out"],
        }
    except Exception as exc:
        logger.error("%s raised an unexpected error: %s", agent_name, exc)
        t = trace_event(agent_name, "error", {"error": str(exc), "message": str(exc)})
        return {"agent_trace": [t], "errors": [f"{agent_name}: {exc}"]}


# ── Retrieval node ────────────────────────────────────────────────────────────

@traceable(name="retrieval_node")
async def retrieval_node(state: AgentState) -> Dict[str, Any]:
    from app.retrieval.hybrid_retriever import HybridRetriever

    t0 = time.perf_counter()
    agent_name = "retrieval"

    events = [
        trace_event(agent_name, "started", {"message": "Preparing hybrid retrieval query"}),
        trace_event(agent_name, "log",     {"message": "Running semantic similarity search (ChromaDB)", "log_type": "info"}),
        trace_event(agent_name, "log",     {"message": "Running BM25 keyword search", "log_type": "info"}),
    ]

    try:
        retriever = HybridRetriever()
        result    = await retriever.retrieve_for_agent(
            query=state["query"],
            top_k=10,
            filters=state.get("filters"),
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        n       = result["total_retrieved"]

        events.append(trace_event(agent_name, "log", {
            "message":  f"CrossEncoder reranker applied — top {n} documents selected",
            "log_type": "info",
        }))
        events.append(trace_event(agent_name, "completed", {
            "message":    f"Retrieved {n} relevant documents",
            "elapsed_ms": elapsed,
        }))

        return {
            "retrieved_incidents": result["documents"],
            "retrieval_scores":    result["scores"],
            "current_agent":       agent_name,
            "elapsed_ms":          elapsed,
            "agent_trace":         events,
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        logger.error("Retrieval node failed: %s", exc, exc_info=True)
        events.append(trace_event(agent_name, "error", {"error": str(exc), "message": str(exc)}, elapsed_ms=elapsed))
        return {
            "retrieved_incidents": [],
            "retrieval_scores":    [],
            "current_agent":       agent_name,
            "agent_trace":         events,
            "errors":              [f"retrieval: {exc}"],
        }


# ── Parallel analysis node (Fix 1 + Fix 6) ────────────────────────────────────

@traceable(name="parallel_analysis")
async def parallel_analysis_node(state: AgentState) -> Dict[str, Any]:
    """Run supplier_risk, shipment_analysis, inventory_intel simultaneously.

    Each agent receives only its most relevant context chunks (Fix 2).
    Each is wrapped in a 25-second timeout (Fix 6).
    Wall-clock time = slowest single agent, not sum of all three.
    """
    def _state_for(agent_name: str) -> AgentState:
        return {**state, "retrieved_incidents": _filter_context(state["retrieved_incidents"], agent_name)}

    s_result, sh_result, i_result = await asyncio.gather(
        _run_with_timeout(supplier_risk_node(_state_for("supplier_risk")),         "supplier_risk"),
        _run_with_timeout(shipment_analysis_node(_state_for("shipment_analysis")), "shipment_analysis"),
        _run_with_timeout(inventory_intel_node(_state_for("inventory_intel")),     "inventory_intel"),
    )

    # Collect trace events from all 3 agents
    all_trace: List[Dict[str, Any]] = []
    all_errors: List[str] = []
    total_tokens = state["tokens_used"]

    for result in (s_result, sh_result, i_result):
        if isinstance(result, dict):
            all_trace.extend(result.get("agent_trace", []))
            all_errors.extend(result.get("errors", []))
            total_tokens += result.get("tokens_used", 0)

    return {
        "supplier_risk_analysis": s_result.get("supplier_risk_analysis")  if isinstance(s_result,  dict) else None,
        "shipment_analysis":       sh_result.get("shipment_analysis")      if isinstance(sh_result, dict) else None,
        "inventory_analysis":      i_result.get("inventory_analysis")      if isinstance(i_result,  dict) else None,
        "agent_trace":             all_trace,
        "tokens_used":             total_tokens,
        "current_agent":           "parallel_analysis",
        "errors":                  all_errors,
    }


# ── Evaluator node ────────────────────────────────────────────────────────────

_JUDGE_SYSTEM_PROMPT = """You are an expert supply chain risk management judge.

Evaluate the quality of the mitigation recommendations provided.

Rate each dimension on a scale of 0-10:
- feasibility: Can the recommended actions actually be implemented given real-world constraints?
- specificity: Are the recommendations specific enough to be actionable (vs generic advice)?
- impact: Will following the recommendations meaningfully reduce supply chain risk?
- timeline_realism: Are the timelines practical and achievable?

Output ONLY valid JSON:
{
  "scores": {
    "feasibility": 0-10,
    "specificity": 0-10,
    "impact": 0-10,
    "timeline_realism": 0-10
  },
  "overall_score": 0-10,
  "verdict": "APPROVED|NEEDS_REVISION|REJECTED",
  "reasoning": "1-2 sentence justification",
  "improvement_suggestions": ["suggestion1", "suggestion2"]
}"""


@traceable(name="evaluator_node")
async def evaluator_node(state: AgentState) -> Dict[str, Any]:
    t0         = time.perf_counter()
    agent_name = "evaluator"
    events     = [
        trace_event(agent_name, "started", {"message": "Evaluating recommendation quality"}),
        trace_event(agent_name, "log",     {"message": "Checking feasibility, specificity, and timeline realism", "log_type": "info"}),
    ]

    import json

    recs_text       = json.dumps(state.get("recommendations", [])[:3], indent=2)  # top 3 recs
    context_snippet = "\n".join(
        d.get("text", "")[:200] for d in state.get("retrieved_incidents", [])[:2]
    )

    user_prompt = (
        f"QUERY: {state['query']}\n\n"
        f"CONTEXT (brief):\n{context_snippet}\n\n"
        f"RECOMMENDATIONS:\n{recs_text}\n\n"
        f"Evaluate concisely."
    )

    try:
        result, tokens = await llm_json_call(_JUDGE_SYSTEM_PROMPT, user_prompt)
        elapsed  = int((time.perf_counter() - t0) * 1000)
        verdict  = result.get("verdict", "NEEDS_REVISION")
        score    = result.get("overall_score", 0)
        log_type = "success" if verdict == "APPROVED" else "warn" if verdict == "NEEDS_REVISION" else "error"

        events.append(trace_event(agent_name, "log", {
            "message":  f"Verdict: {verdict} — overall score {score:.1f}/10",
            "log_type": log_type,
        }))
        events.append(trace_event(agent_name, "completed", {
            "message":    f"{verdict} — score {score:.1f}/10",
            "tokens_used": tokens,
            "elapsed_ms":  elapsed,
        }))

        return {
            "evaluation_scores": result,
            "current_agent":     agent_name,
            "tokens_used":       state["tokens_used"] + tokens,
            "elapsed_ms":        elapsed,
            "agent_trace":       events,
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        logger.warning("Evaluator node failed (non-fatal): %s", exc)
        events.append(trace_event(agent_name, "error", {"error": str(exc), "message": str(exc)}, elapsed_ms=elapsed))
        return {
            "evaluation_scores": {"scores": {}, "overall_score": 0.0, "verdict": "NEEDS_REVISION", "reasoning": str(exc)},
            "current_agent":     agent_name,
            "agent_trace":       events,
            "errors":            [f"evaluator: {exc}"],
        }


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph() -> Any:
    """Pipeline: retrieval → parallel_analysis (3 agents) → recommendation → evaluator → END."""
    builder = StateGraph(AgentState)

    builder.add_node("retrieval",         retrieval_node)
    builder.add_node("parallel_analysis", parallel_analysis_node)
    builder.add_node("recommendation",    recommendation_node)
    builder.add_node("evaluator",         evaluator_node)

    builder.set_entry_point("retrieval")
    builder.add_edge("retrieval",         "parallel_analysis")
    builder.add_edge("parallel_analysis", "recommendation")
    builder.add_edge("recommendation",    "evaluator")
    builder.add_edge("evaluator",         END)

    return builder.compile()


def _get_compiled_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
        logger.info("LangGraph compiled.")
    return _compiled_graph


# ── Initial state factory ─────────────────────────────────────────────────────

def _make_initial_state(
    query: str,
    session_id: str,
    user_id: str = "anonymous",
    filters: Optional[Dict[str, Any]] = None,
) -> AgentState:
    return AgentState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        filters=filters or {},
        retrieved_incidents=[],
        retrieval_scores=[],
        supplier_risk_analysis=None,
        shipment_analysis=None,
        inventory_analysis=None,
        recommendations=[],
        final_response=None,
        risk_score=None,
        evaluation_scores=None,
        agent_trace=[],
        current_agent=None,
        tokens_used=0,
        elapsed_ms=0,
        errors=[],
    )


# ── Public streaming interface ────────────────────────────────────────────────

async def run_agent_graph_stream(
    query: str,
    session_id: str,
    user_id: str = "anonymous",
    filters: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    graph         = _get_compiled_graph()
    initial_state = _make_initial_state(query, session_id, user_id, filters)
    global_start  = time.perf_counter()

    accumulated: Dict[str, Any] = {
        "recommendations":   [],
        "risk_score":        None,
        "final_response":    None,
        "evaluation_scores": None,
        "tokens_used":       0,
    }

    async for chunk in graph.astream(initial_state):
        node_name   = next(iter(chunk))
        node_output: Dict[str, Any] = chunk[node_name]

        # After retrieval completes, immediately signal that parallel agents are starting.
        # This lets the frontend show all 3 boxes as "running" during the ~20s wait.
        if node_name == "retrieval" and not node_output.get("errors"):
            ts = datetime.now(timezone.utc).isoformat()
            for agent_name in ("supplier_risk", "shipment_analysis", "inventory_intel"):
                yield {
                    "type":       "agent_started",
                    "agent":      agent_name,
                    "data":       {"message": "Starting parallel analysis"},
                    "timestamp":  ts,
                    "elapsed_ms": 0,
                    "tokens_used": 0,
                }

        for event in node_output.get("agent_trace", []):
            yield event

        for field in ("recommendations", "risk_score", "final_response",
                      "evaluation_scores", "tokens_used"):
            if field in node_output and node_output[field] is not None:
                accumulated[field] = node_output[field]

    total_ms = int((time.perf_counter() - global_start) * 1000)
    yield {
        "type":  "final_result",
        "agent": "system",
        "data": {
            "recommendations":   accumulated["recommendations"],
            "risk_score":        accumulated["risk_score"],
            "final_response":    accumulated["final_response"],
            "evaluation_scores": accumulated["evaluation_scores"],
        },
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "total_elapsed_ms": total_ms,
        "tokens_used":      accumulated["tokens_used"],
    }
    yield {
        "type":      "pipeline_done",
        "agent":     "system",
        "data":      {"total_elapsed_ms": total_ms},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def run_agent_graph_sync(
    query: str,
    session_id: str,
    user_id: str = "anonymous",
    filters: Optional[Dict[str, Any]] = None,
) -> AgentState:
    graph = _get_compiled_graph()
    return await graph.ainvoke(_make_initial_state(query, session_id, user_id, filters))
