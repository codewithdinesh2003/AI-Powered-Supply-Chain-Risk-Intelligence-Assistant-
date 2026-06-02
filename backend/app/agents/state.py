from __future__ import annotations

from operator import add
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict


class AgentState(TypedDict):
    # ── Input ────────────────────────────────────────────────────────────
    query: str
    session_id: str
    user_id: str
    filters: Dict[str, Any]          # metadata filters forwarded to retrieval

    # ── Retrieved context ────────────────────────────────────────────────
    retrieved_incidents: List[Dict[str, Any]]   # list of RetrievedDocument.to_dict()
    retrieval_scores: List[float]

    # ── Per-agent analysis outputs ────────────────────────────────────────
    supplier_risk_analysis: Optional[Dict[str, Any]]
    shipment_analysis: Optional[Dict[str, Any]]
    inventory_analysis: Optional[Dict[str, Any]]

    # ── Final output ──────────────────────────────────────────────────────
    recommendations: List[Dict[str, Any]]
    final_response: Optional[str]       # formatted executive summary
    risk_score: Optional[float]         # 0–100

    # ── Evaluation ────────────────────────────────────────────────────────
    evaluation_scores: Optional[Dict[str, Any]]

    # ── Observability / streaming ─────────────────────────────────────────
    # Annotated with `add` so each node APPENDS to the list rather than
    # replacing it — enabling a running trace across all nodes.
    agent_trace: Annotated[List[Dict[str, Any]], add]
    current_agent: Optional[str]
    tokens_used: int
    elapsed_ms: int
    errors: Annotated[List[str], add]
