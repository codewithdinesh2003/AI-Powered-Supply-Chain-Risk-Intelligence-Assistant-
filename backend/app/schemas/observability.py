from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class LangSmithRun(BaseModel):
    run_id: str
    name: str
    status: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    latency_ms: Optional[int]
    total_tokens: Optional[int]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    query_snippet: Optional[str]
    error: Optional[str]


class AgentStats(BaseModel):
    agent_name: str
    avg_latency_ms: float
    total_calls: int
    error_rate: float
    avg_tokens: float


class ObservabilityMetrics(BaseModel):
    total_queries_today: int
    avg_latency_ms: float
    avg_evaluation_score: Optional[float]
    estimated_cost_today_usd: float
    success_rate: float
    total_tokens_today: int
    per_agent_stats: List[AgentStats]
    queries_over_time: List[Dict[str, Any]]   # [{date, count}]
    quality_over_time: List[Dict[str, Any]]   # [{date, score}]


class TraceDetail(BaseModel):
    run_id: str
    query: Optional[str]
    status: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    latency_ms: Optional[int]
    total_tokens: Optional[int]
    agent_steps: List[Dict[str, Any]]
    retrieved_docs_count: Optional[int]
    evaluation_scores: Optional[Dict[str, Any]]
    error: Optional[str]


class EvaluationResultResponse(BaseModel):
    id: str
    session_id: str
    answer_relevancy: Optional[float]
    faithfulness: Optional[float]
    contextual_recall: Optional[float]
    contextual_precision: Optional[float]
    judge_feasibility: Optional[float]
    judge_specificity: Optional[float]
    judge_impact: Optional[float]
    judge_timeline_realism: Optional[float]
    judge_overall: Optional[float]
    judge_verdict: Optional[str]
    judge_reasoning: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
