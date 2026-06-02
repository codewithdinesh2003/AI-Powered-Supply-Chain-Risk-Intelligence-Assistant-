"""LangGraph StateGraph definition and async streaming runner."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional

from langsmith import traceable
from langgraph.graph import END, StateGraph

from app.agents._common import llm_json_call, trace_event
from app.agents.inventory_intel import inventory_intel_node
from app.agents.recommendation import recommendation_node
from app.agents.shipment_analysis import shipment_analysis_node
from app.agents.state import AgentState
from app.agents.supplier_risk import supplier_risk_node

logger = logging.getLogger(__name__)

# Module-level compiled graph — built once on first import
_compiled_graph: Any = None


# ── Retrieval node ────────────────────────────────────────────────────────────

@traceable(name="retrieval_node")
async def retrieval_node(state: AgentState) -> Dict[str, Any]:
    from app.retrieval.hybrid_retriever import HybridRetriever

    t0 = time.perf_counter()
    agent_name = "retrieval"
    started = trace_event(agent_name, "started")

    try:
        retriever = HybridRetriever()
        result = await retriever.retrieve_for_agent(
            query=state["query"],
            top_k=10,
            filters=state.get("filters"),
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        done = trace_event(
            agent_name, "completed",
            {"total_retrieved": result["total_retrieved"]},
            elapsed_ms=elapsed,
        )
        return {
            "retrieved_incidents": result["documents"],
            "retrieval_scores": result["scores"],
            "current_agent": agent_name,
            "elapsed_ms": elapsed,
            "agent_trace": [started, done],
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        logger.error("Retrieval node failed: %s", exc, exc_info=True)
        err = trace_event(agent_name, "error", {"error": str(exc)}, elapsed_ms=elapsed)
        return {
            "retrieved_incidents": [],
            "retrieval_scores": [],
            "current_agent": agent_name,
            "agent_trace": [started, err],
            "errors": [f"retrieval: {exc}"],
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
    t0 = time.perf_counter()
    agent_name = "evaluator"
    started = trace_event(agent_name, "started")

    import json

    recs_text = json.dumps(state.get("recommendations", []), indent=2)
    context_snippet = "\n".join(
        d.get("text", "")[:300] for d in state.get("retrieved_incidents", [])[:3]
    )

    user_prompt = (
        f"QUERY: {state['query']}\n\n"
        f"CONTEXT USED:\n{context_snippet}\n\n"
        f"RECOMMENDATIONS GENERATED:\n{recs_text}\n\n"
        f"Evaluate the quality of these recommendations."
    )

    try:
        result, tokens = await llm_json_call(_JUDGE_SYSTEM_PROMPT, user_prompt)
        elapsed = int((time.perf_counter() - t0) * 1000)
        done = trace_event(agent_name, "completed", result, elapsed_ms=elapsed, tokens=tokens)

        return {
            "evaluation_scores": result,
            "current_agent": agent_name,
            "tokens_used": state["tokens_used"] + tokens,
            "elapsed_ms": elapsed,
            "agent_trace": [started, done],
        }

    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        logger.warning("Evaluator node failed (non-fatal): %s", exc)
        err = trace_event(agent_name, "error", {"error": str(exc)}, elapsed_ms=elapsed)
        return {
            "evaluation_scores": {
                "scores": {}, "overall_score": 0.0,
                "verdict": "NEEDS_REVISION", "reasoning": str(exc),
            },
            "current_agent": agent_name,
            "agent_trace": [started, err],
            "errors": [f"evaluator: {exc}"],
        }


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph() -> Any:
    """Construct and compile the LangGraph StateGraph.

    Pipeline (sequential for reliability):
    retrieval → supplier_risk → shipment_analysis → inventory_intel
              → recommendation → evaluator → END
    """
    builder = StateGraph(AgentState)

    builder.add_node("retrieval", retrieval_node)
    builder.add_node("supplier_risk", supplier_risk_node)
    builder.add_node("shipment_analysis", shipment_analysis_node)
    builder.add_node("inventory_intel", inventory_intel_node)
    builder.add_node("recommendation", recommendation_node)
    builder.add_node("evaluator", evaluator_node)

    builder.set_entry_point("retrieval")

    builder.add_edge("retrieval", "supplier_risk")
    builder.add_edge("supplier_risk", "shipment_analysis")
    builder.add_edge("shipment_analysis", "inventory_intel")
    builder.add_edge("inventory_intel", "recommendation")
    builder.add_edge("recommendation", "evaluator")
    builder.add_edge("evaluator", END)

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
    """Stream agent trace events as the graph executes.

    Yields SSE-ready dicts — one per agent_trace event plus a final
    ``final_result`` event when the evaluator completes.
    """
    graph = _get_compiled_graph()
    initial_state = _make_initial_state(query, session_id, user_id, filters)
    global_start = time.perf_counter()

    final_state: Optional[AgentState] = None

    async for chunk in graph.astream(initial_state):
        node_name = next(iter(chunk))
        node_output: Dict[str, Any] = chunk[node_name]

        # Emit each trace event the node produced
        for event in node_output.get("agent_trace", []):
            yield event

        # Track the latest full state via accumulation
        # (astream gives us deltas; we only need the final one)
        if node_name == "evaluator":
            final_state = node_output

    # Emit the synthesised final_result event
    total_ms = int((time.perf_counter() - global_start) * 1000)
    yield {
        "type": "final_result",
        "agent": "system",
        "data": {
            "recommendations": final_state.get("recommendations", []) if final_state else [],
            "risk_score": final_state.get("risk_score") if final_state else None,
            "final_response": final_state.get("final_response") if final_state else "",
            "evaluation_scores": final_state.get("evaluation_scores") if final_state else {},
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_elapsed_ms": total_ms,
        "tokens_used": final_state.get("tokens_used", 0) if final_state else 0,
    }


async def run_agent_graph_sync(
    query: str,
    session_id: str,
    user_id: str = "anonymous",
    filters: Optional[Dict[str, Any]] = None,
) -> AgentState:
    """Non-streaming version — waits for full graph completion and returns state."""
    graph = _get_compiled_graph()
    initial_state = _make_initial_state(query, session_id, user_id, filters)
    return await graph.ainvoke(initial_state)
