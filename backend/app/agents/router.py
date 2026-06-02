"""LangGraph routing functions — decide which node to visit next."""
from __future__ import annotations

from typing import Literal

from app.agents.state import AgentState


def route_after_retrieval(state: AgentState) -> Literal["supplier_risk"]:
    """After retrieval, always start the sequential analysis pipeline."""
    return "supplier_risk"


def route_after_supplier_risk(state: AgentState) -> Literal["shipment_analysis"]:
    return "shipment_analysis"


def route_after_shipment(state: AgentState) -> Literal["inventory_intel"]:
    return "inventory_intel"


def route_after_inventory(state: AgentState) -> Literal["recommendation"]:
    return "recommendation"


def route_after_recommendation(state: AgentState) -> Literal["evaluator"]:
    return "evaluator"
