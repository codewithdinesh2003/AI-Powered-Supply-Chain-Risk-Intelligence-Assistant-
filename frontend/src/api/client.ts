import axios, { type AxiosInstance } from 'axios'
import { QueryClient } from '@tanstack/react-query'
import type {
  AlertItem,
  ApiResponse,
  AuthTokens,
  DashboardKPIs,
  EvaluationScores,
  Incident,
  LangSmithRun,
  ObservabilityMetrics,
  QueryRequest,
  QueryResult,
  QuerySessionSummary,
  Supplier,
  User,
} from '../types'

// ── Axios instance ────────────────────────────────────────────────────────

export const api: AxiosInstance = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 120_000,
})

// Attach JWT from localStorage on every request
api.interceptors.request.use((config) => {
  try {
    const stored = localStorage.getItem('scm-intel-store')
    if (stored) {
      const parsed = JSON.parse(stored)
      const token = parsed?.state?.accessToken
      if (token) config.headers.Authorization = `Bearer ${token}`
    }
  } catch {
    /* ignore parse errors */
  }
  return config
})

// Redirect to /login on 401
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('scm-intel-store')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ── TanStack Query client ─────────────────────────────────────────────────

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// ── Helper ────────────────────────────────────────────────────────────────

async function unwrap<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const { data } = await promise
  if (!data.success) throw new Error(data.error ?? 'Request failed')
  return data.data
}

// ── Auth ──────────────────────────────────────────────────────────────────

export const authApi = {
  login:    (email: string, password: string) =>
    unwrap<AuthTokens>(api.post('/auth/login', { email, password })),
  register: (email: string, password: string, full_name: string) =>
    unwrap<User>(api.post('/auth/register', { email, password, full_name })),
  me:       () => unwrap<User>(api.get('/auth/me')),
  refresh:  (refresh_token: string) =>
    unwrap<{ access_token: string; token_type: string }>(api.post('/auth/refresh', { refresh_token })),
}

// ── Query (non-streaming) ─────────────────────────────────────────────────

export const queryApi = {
  sync:         (req: QueryRequest) =>
    unwrap<QueryResult>(api.post('/query/sync', req)),
  sessions:     (skip = 0, limit = 20) =>
    unwrap<QuerySessionSummary[]>(api.get('/query/sessions', { params: { skip, limit } })),
  getSession:   (sessionId: string) =>
    unwrap<QuerySessionSummary>(api.get(`/query/sessions/${sessionId}`)),
}

// ── Incidents ─────────────────────────────────────────────────────────────

export const incidentsApi = {
  list: (params?: Record<string, string | number>) =>
    unwrap<Incident[]>(api.get('/incidents', { params })),
  get:    (id: string) => unwrap<Incident>(api.get(`/incidents/${id}`)),
  create: (data: Partial<Incident>) => unwrap<Incident>(api.post('/incidents', data)),
  update: (id: string, data: Partial<Incident>) => unwrap<Incident>(api.put(`/incidents/${id}`, data)),
  delete: (id: string) => api.delete(`/incidents/${id}`),
  stats:  () => unwrap<{ total: number; open: number; by_severity: Record<string, number> }>(
    api.get('/incidents/stats/summary')
  ),
}

// ── Suppliers ─────────────────────────────────────────────────────────────

export const suppliersApi = {
  list:    (params?: Record<string, string | number>) =>
    unwrap<Supplier[]>(api.get('/suppliers', { params })),
  get:     (id: string) => unwrap<Supplier>(api.get(`/suppliers/${id}`)),
  history: (id: string, limit = 30) =>
    unwrap<Array<Record<string, unknown>>>(api.get(`/suppliers/${id}/history`, { params: { limit } })),
  stats:   () => unwrap<Record<string, unknown>>(api.get('/suppliers/stats/risk-summary')),
}

// ── Dashboard ─────────────────────────────────────────────────────────────

export const dashboardApi = {
  kpis:   () => unwrap<DashboardKPIs>(api.get('/dashboard/kpis')),
  alerts: (limit = 20) => unwrap<AlertItem[]>(api.get('/dashboard/alerts', { params: { limit } })),
}

// ── Observability ─────────────────────────────────────────────────────────

export const observabilityApi = {
  runs:       (limit = 50) => unwrap<LangSmithRun[]>(api.get('/observability/runs', { params: { limit } })),
  metrics:    () => unwrap<ObservabilityMetrics>(api.get('/observability/metrics')),
  trace:      (runId: string) => unwrap<Record<string, unknown>>(api.get(`/observability/trace/${runId}`)),
  agentStats: () => unwrap<Record<string, unknown>[]>(api.get('/observability/agent-stats')),
}

// ── Evaluation ────────────────────────────────────────────────────────────

export const evaluationApi = {
  run:     (sessionId: string) =>
    unwrap<EvaluationScores>(api.post('/evaluation/run', { session_id: sessionId })),
  results: (skip = 0, limit = 20) =>
    unwrap<EvaluationScores[]>(api.get('/evaluation/results', { params: { skip, limit } })),
}

// ── Upload ────────────────────────────────────────────────────────────────

export interface UploadJob {
  job_id: string
  filename: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  step: string
  progress: number
  total_records: number
  records_processed: number
  suppliers_detected: number
  errors: string[]
  created_at: string
  completed_at: string | null
}

export const uploadApi = {
  uploadCSV: async (file: File): Promise<{ job_id: string; status: string; message: string }> => {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/upload/csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return (res.data as any).data
  },
  status:  (jobId: string) => unwrap<UploadJob>(api.get(`/upload/status/${jobId}`)),
  history: ()              => unwrap<UploadJob[]>(api.get('/upload/history')),
}

// ── ETL ───────────────────────────────────────────────────────────────────

export interface FieldMappingSpec {
  source_column: string | null
  transform: 'direct' | 'derive' | 'divide_by_100' | 'negate' | 'date_parse' | 'slugify'
  derive_formula: string | null
  confidence: number
}

export interface DetectionResult {
  temp_file_id: string
  filename: string
  row_count: number
  detected_mapping: {
    mappings: Record<string, FieldMappingSpec>
    missing_fields: string[]
    notes: string
    source_columns: string[]
  }
  saved_mapping: Record<string, unknown> | null
}

export interface ETLJob {
  job_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  step: string
  progress: number
  records_processed: number
  suppliers_detected: number
  errors: string[]
  result: Record<string, unknown> | null
  created_at: string
}

export interface CompanyMapping {
  id: string
  company_id: string
  company_name: string
  mapping_config: Record<string, FieldMappingSpec>
  source_columns: string[]
  confidence_score: number
  created_at: string
  last_used_at: string | null
}

export const etlApi = {
  detect: async (file: File): Promise<DetectionResult> => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await api.post('/etl/detect', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    return (res.data as any).data
  },

  preview: (tempFileId: string, mapping: Record<string, FieldMappingSpec>) =>
    unwrap<{ rows: Record<string, unknown>[]; count: number }>(
      api.post('/etl/preview', { temp_file_id: tempFileId, mapping })
    ),

  run: (tempFileId: string, mapping: Record<string, FieldMappingSpec>,
        companyId: string, companyName: string, saveMapping: boolean) =>
    unwrap<{ job_id: string; status: string; message: string }>(
      api.post('/etl/run', {
        temp_file_id: tempFileId, mapping,
        company_id: companyId, company_name: companyName, save_mapping: saveMapping,
      })
    ),

  jobStatus: (jobId: string) => unwrap<ETLJob>(api.get(`/etl/jobs/${jobId}`)),

  listMappings: ()              => unwrap<CompanyMapping[]>(api.get('/etl/mappings')),
  saveMapping:  (data: unknown) => unwrap<{ id: string }>(api.post('/etl/mappings', data)),
  deleteMapping:(id: string)    => api.delete(`/etl/mappings/${id}`),
}

// ── SSE stream helper ─────────────────────────────────────────────────────

export function createQueryStream(
  request: QueryRequest,
  onEvent: (event: Record<string, unknown>) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  onSessionId?: (sessionId: string) => void
): () => void {
  const controller = new AbortController()

  ;(async () => {
    try {
      const stored = localStorage.getItem('scm-intel-store')
      let token = ''
      if (stored) {
        try { token = JSON.parse(stored)?.state?.accessToken ?? '' } catch { /* */ }
      }

      const response = await fetch('/api/query/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(request),
        signal: controller.signal,
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      // Capture the server-assigned session ID from response header
      const sessionId = response.headers.get('X-Session-Id')
      if (sessionId && onSessionId) {
        onSessionId(sessionId)
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          const data = line.replace(/^data:\s*/, '').trim()
          if (data) {
            try { onEvent(JSON.parse(data)) } catch { /* skip malformed */ }
          }
        }
      }
      onDone()
    } catch (err) {
      if ((err as Error).name !== 'AbortError') onError(err as Error)
    }
  })()

  return () => controller.abort()
}
