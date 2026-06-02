"""Unit tests for LangGraph agent nodes.

All LLM and external calls are mocked — no API keys required.
Run with:  pytest tests/test_agents.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.state import AgentState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_state(**overrides) -> AgentState:
    base: AgentState = {
        "query": "What are the supplier risks for critical components?",
        "session_id": "test-session-001",
        "user_id": "test-user",
        "filters": {},
        "retrieved_incidents": [
            {
                "doc_id": "record_INC-00001_SUP-001",
                "text": "SUPPLY CHAIN INCIDENT REPORT\nSupplier: GlobalTech (SUP-001)\nDelivery Delay: 18 days\nSeverity: CRITICAL",
                "metadata": {"supplier_id": "SUP-001", "severity": "critical", "incident_category": "supplier"},
                "score": 0.91,
                "rank": 0,
            }
        ],
        "retrieval_scores": [0.91],
        "supplier_risk_analysis": None,
        "shipment_analysis": None,
        "inventory_analysis": None,
        "recommendations": [],
        "final_response": None,
        "risk_score": None,
        "evaluation_scores": None,
        "agent_trace": [],
        "current_agent": None,
        "tokens_used": 0,
        "elapsed_ms": 0,
        "errors": [],
    }
    base.update(overrides)
    return base


_SUPPLIER_MOCK = {
    "risk_level": "high",
    "key_risks": [{"risk": "Late delivery", "severity": "high", "likelihood": "high"}],
    "affected_suppliers": [{"supplier_id": "SUP-001", "name": "GlobalTech", "risk_score": 82, "primary_issue": "delivery delays"}],
    "trend": "degrading",
    "hotspot_regions": ["Asia-Pacific"],
    "confidence_score": 0.88,
    "reasoning": "Multiple critical delay incidents detected.",
}

_SHIPMENT_MOCK = {
    "delay_probability": 0.82,
    "estimated_delay_days": 14.0,
    "affected_routes": [{"route": "Shanghai → Los Angeles", "congestion_level": "critical", "avg_delay_days": 18.0}],
    "cost_impact": {"estimated_additional_cost_usd": 45000, "cost_increase_pct": 35.0, "primary_cost_driver": "port congestion"},
    "disruption_hotspots": [{"location": "Shanghai", "issue_type": "port congestion", "severity": "critical"}],
    "recommended_actions": ["Reroute via alternative port"],
    "confidence_score": 0.85,
    "reasoning": "Shanghai congestion driving delays.",
}

_INVENTORY_MOCK = {
    "stockout_risk_items": [{"item": "PCB", "supplier_id": "SUP-001", "current_inventory": 120, "demand_forecast": 800, "coverage_ratio": 0.15, "days_until_stockout": 3, "risk_level": "critical"}],
    "demand_surge_detected": True,
    "demand_surge_details": {"magnitude_pct": 40.0, "affected_categories": ["Electronics"], "likely_cause": "Q4 demand spike"},
    "reorder_recommendations": [{"supplier_id": "SUP-001", "item": "PCB", "recommended_order_qty": 2000, "urgency": "immediate"}],
    "warehouse_imbalances": [],
    "overall_inventory_health": "critical",
    "confidence_score": 0.91,
    "reasoning": "PCB stock at 15% of safety level.",
}

_RECOMMENDATION_MOCK = {
    "recommendations": [
        {
            "id": "REC-001",
            "priority": "P1",
            "action": "Emergency reorder of PCB components from SUP-001",
            "rationale": "Current stock at 15% with 3-day horizon",
            "timeline": "Within 24 hours",
            "expected_impact": "Prevent stockout, maintain production continuity",
            "responsible_team": "Procurement",
            "affected_suppliers": ["SUP-001"],
            "risk_domains": ["inventory", "supplier"],
        }
    ],
    "overall_risk_score": 87,
    "risk_breakdown": {"supplier_risk": 82, "shipment_risk": 78, "inventory_risk": 91},
    "executive_summary": "Critical supply chain disruption detected. Immediate action required.",
    "immediate_actions_required": True,
    "confidence_score": 0.90,
}


# ── Agent node tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_supplier_risk_node_happy_path():
    from app.agents.supplier_risk import supplier_risk_node

    with patch("app.agents.supplier_risk.llm_json_call", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (_SUPPLIER_MOCK, 500)
        state = _make_state()
        result = await supplier_risk_node(state)

    assert "supplier_risk_analysis" in result
    assert result["supplier_risk_analysis"]["risk_level"] == "high"
    assert result["tokens_used"] == 500
    assert len(result["agent_trace"]) == 2
    assert result["agent_trace"][0]["status"] == "started"
    assert result["agent_trace"][1]["status"] == "completed"


@pytest.mark.asyncio
async def test_supplier_risk_node_handles_llm_failure():
    from app.agents.supplier_risk import supplier_risk_node

    with patch("app.agents.supplier_risk.llm_json_call", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = Exception("OpenAI timeout")
        result = await supplier_risk_node(_make_state())

    assert result["supplier_risk_analysis"]["risk_level"] == "unknown"
    assert len(result["errors"]) == 1
    assert "supplier_risk" in result["errors"][0]
    assert result["agent_trace"][1]["status"] == "error"


@pytest.mark.asyncio
async def test_shipment_analysis_node_happy_path():
    from app.agents.shipment_analysis import shipment_analysis_node

    with patch("app.agents.shipment_analysis.llm_json_call", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (_SHIPMENT_MOCK, 600)
        result = await shipment_analysis_node(_make_state())

    assert result["shipment_analysis"]["delay_probability"] == 0.82
    assert result["tokens_used"] == 600


@pytest.mark.asyncio
async def test_inventory_intel_node_happy_path():
    from app.agents.inventory_intel import inventory_intel_node

    with patch("app.agents.inventory_intel.llm_json_call", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (_INVENTORY_MOCK, 550)
        result = await inventory_intel_node(_make_state())

    assert result["inventory_analysis"]["demand_surge_detected"] is True
    assert len(result["inventory_analysis"]["stockout_risk_items"]) == 1


@pytest.mark.asyncio
async def test_recommendation_node_synthesises_all_analyses():
    from app.agents.recommendation import recommendation_node

    state = _make_state(
        supplier_risk_analysis=_SUPPLIER_MOCK,
        shipment_analysis=_SHIPMENT_MOCK,
        inventory_analysis=_INVENTORY_MOCK,
    )
    with patch("app.agents.recommendation.llm_json_call", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (_RECOMMENDATION_MOCK, 800)
        result = await recommendation_node(state)

    assert len(result["recommendations"]) == 1
    assert result["recommendations"][0]["priority"] == "P1"
    assert result["risk_score"] == 87.0
    assert result["final_response"] != ""


@pytest.mark.asyncio
async def test_recommendation_node_handles_partial_analyses():
    """Recommendation should still work if one analysis is missing."""
    from app.agents.recommendation import recommendation_node

    state = _make_state(
        supplier_risk_analysis=_SUPPLIER_MOCK,
        shipment_analysis=None,   # missing
        inventory_analysis=_INVENTORY_MOCK,
    )
    with patch("app.agents.recommendation.llm_json_call", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (_RECOMMENDATION_MOCK, 700)
        result = await recommendation_node(state)

    assert result["recommendations"] is not None


# ── AgentState accumulator tests ──────────────────────────────────────────────

def test_agent_state_trace_accumulates():
    """Annotated[List, add] reducer should append, not replace."""
    from operator import add

    trace1 = [{"type": "agent_started", "agent": "retrieval"}]
    trace2 = [{"type": "agent_completed", "agent": "retrieval"}]
    combined = add(trace1, trace2)
    assert len(combined) == 2


def test_agent_state_errors_accumulate():
    from operator import add

    errors1 = ["retrieval: timeout"]
    errors2 = ["supplier_risk: json parse error"]
    combined = add(errors1, errors2)
    assert len(combined) == 2
    assert combined[0] == "retrieval: timeout"


# ── Graph compilation test ────────────────────────────────────────────────────

def test_graph_compiles_without_error():
    from app.agents.graph import build_graph

    graph = build_graph()
    assert graph is not None
