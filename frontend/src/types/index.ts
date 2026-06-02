// ── Agent / Graph ──────────────────────────────────────────────────────────

export type AgentStatus = 'idle' | 'running' | 'completed' | 'error'

export interface AgentTraceEvent {
  type: string            // 'agent_started' | 'agent_thinking' | 'agent_completed' | 'final_result' | 'error'
  agent: string
  status?: string
  data: Record<string, unknown>
  timestamp: string
  elapsed_ms: number
  tokens_used: number
  total_elapsed_ms?: number
}

export interface AgentNodeData {
  label: string
  role: string
  status: AgentStatus
  output?: Record<string, unknown>
  elapsed_ms?: number
  tokens?: number
}

// ── Query ─────────────────────────────────────────────────────────────────

export interface QueryRequest {
  query: string
  session_id?: string
  filters?: QueryFilters
}

export interface QueryFilters {
  supplier_id?: string
  severity?: string | string[]
  category?: string
  warehouse_location?: string
  date_from?: string
  date_to?: string
}

export interface Recommendation {
  id?: string
  priority: 'P1' | 'P2' | 'P3'
  action: string
  rationale: string
  timeline: string
  expected_impact: string
  responsible_team: string
  affected_suppliers: string[]
  risk_domains: string[]
  judgment?: JudgmentResult
}

export interface JudgmentResult {
  scores: { feasibility: number; specificity: number; impact: number; timeline_realism: number }
  overall_score: number
  verdict: 'APPROVED' | 'NEEDS_REVISION' | 'REJECTED'
  reasoning: string
  improvement_suggestions: string[]
}

export interface QueryResult {
  session_id: string
  query: string
  recommendations: Recommendation[]
  risk_score: number | null
  final_response: string | null
  evaluation_scores: EvaluationScores | null
  retrieved_incidents: RetrievedDoc[]
  agent_trace: AgentTraceEvent[]
  tokens_used: number
  elapsed_ms: number
  errors: string[]
}

export interface QuerySessionSummary {
  id: string
  session_id: string
  query_text: string
  risk_score: number | null
  tokens_used: number
  latency_ms: number | null
  evaluation_score: number | null
  judge_verdict: string | null
  created_at: string
}

// ── Retrieval ─────────────────────────────────────────────────────────────

export interface RetrievedDoc {
  doc_id: string
  text: string
  metadata: Record<string, unknown>
  score: number
  rank: number
}

// ── Incidents ────────────────────────────────────────────────────────────

export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type IncidentCategory = 'supplier' | 'shipment' | 'inventory' | 'demand'
export type ResolutionStatus = 'open' | 'in_progress' | 'resolved' | 'closed'

export interface Incident {
  id: string
  incident_code: string
  title: string
  description?: string
  severity: Severity
  category: IncidentCategory
  supplier_ref?: string
  warehouse_location?: string
  shipment_status?: string
  delivery_delay_days?: number
  transportation_cost?: number
  inventory_level?: number
  demand_forecast?: number
  impact_score?: number
  resolution_status: ResolutionStatus
  resolution_notes?: string
  occurred_at?: string
  resolved_at?: string
  created_at: string
  updated_at: string
}

// ── Suppliers ────────────────────────────────────────────────────────────

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface Supplier {
  id: string
  supplier_id: string
  name: string
  region?: string
  category?: string
  reliability_score?: number
  avg_delay_days?: number
  active_orders: number
  risk_level: RiskLevel
  last_updated: string
  recent_incidents?: Partial<Incident>[]
}

// ── Dashboard ─────────────────────────────────────────────────────────────

export interface DashboardKPIs {
  overall_risk_score: number
  active_incidents: {
    total: number
    by_severity: Record<Severity, number>
  }
  supplier_health: {
    pct_healthy: number
    avg_reliability_score: number
    total_suppliers: number
  }
  shipment_on_time_rate: number
  ai_queries: {
    today: number
    avg_quality_score: number | null
  }
  recent_sessions: QuerySessionSummary[]
}

export interface AlertItem {
  id: string
  incident_code: string
  title: string
  severity: Severity
  category: IncidentCategory
  supplier_ref?: string
  warehouse_location?: string
  shipment_status?: string
  delivery_delay_days?: number
  impact_score?: number
  occurred_at?: string
  resolution_status: ResolutionStatus
}

// ── Observability ─────────────────────────────────────────────────────────

export interface EvaluationScores {
  answer_relevancy?: number
  faithfulness?: number
  contextual_recall?: number
  contextual_precision?: number
  average_score?: number
  overall_score?: number
  verdict?: string
  reasoning?: string
  scores?: Record<string, number>
  improvement_suggestions?: string[]
}

export interface AgentStat {
  agent_name: string
  avg_latency_ms: number
  total_calls: number
  error_rate: number
  avg_tokens: number
}

export interface ObservabilityMetrics {
  total_queries_today: number
  avg_latency_ms: number
  avg_evaluation_score: number | null
  estimated_cost_today_usd: number
  success_rate: number
  total_tokens_today: number
  per_agent_stats: AgentStat[]
  queries_over_time: Array<{ date: string; count: number }>
  quality_over_time: Array<{ date: string; score: number }>
}

export interface LangSmithRun {
  run_id: string
  name: string
  status: string
  start_time: string | null
  end_time: string | null
  latency_ms: number | null
  total_tokens: number | null
  query_snippet: string | null
  error: string | null
}

// ── Auth ──────────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  full_name: string
  role: 'analyst' | 'manager' | 'admin'
  is_active: boolean
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

// ── API Response envelope ─────────────────────────────────────────────────

export interface ApiResponse<T> {
  success: boolean
  data: T
  meta: Record<string, unknown>
  error?: string
}
