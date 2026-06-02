from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=2000, description="Natural language supply chain query")
    session_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Metadata filters for retrieval")

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()


class AgentTraceEvent(BaseModel):
    type: str
    agent: str
    status: Optional[str] = None
    data: Dict[str, Any] = {}
    timestamp: str
    elapsed_ms: int = 0
    tokens_used: int = 0


class RecommendationItem(BaseModel):
    id: Optional[str] = None
    priority: str          # P1 | P2 | P3
    action: str
    rationale: str
    timeline: str
    expected_impact: str
    responsible_team: str
    affected_suppliers: List[str] = []
    risk_domains: List[str] = []


class QueryResult(BaseModel):
    session_id: str
    query: str
    recommendations: List[Dict[str, Any]]
    risk_score: Optional[float]
    final_response: Optional[str]
    evaluation_scores: Optional[Dict[str, Any]]
    retrieved_incidents: List[Dict[str, Any]]
    agent_trace: List[Dict[str, Any]]
    tokens_used: int
    elapsed_ms: int
    errors: List[str] = []


class QuerySessionSummary(BaseModel):
    id: str
    session_id: str
    query_text: str
    risk_score: Optional[float]
    tokens_used: int
    latency_ms: Optional[int]
    evaluation_score: Optional[float]
    judge_verdict: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class QuerySessionDetail(QuerySessionSummary):
    agent_trace: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]
    retrieval_context: Optional[Dict[str, Any]]
    deepeval_scores: Optional[Dict[str, Any]]
