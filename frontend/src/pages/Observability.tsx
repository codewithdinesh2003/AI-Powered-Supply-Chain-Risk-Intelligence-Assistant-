import { useQuery } from '@tanstack/react-query'
import { Activity, Clock, DollarSign, Zap } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts'
import { evaluationApi, observabilityApi } from '../api/client'
import { Card, KPICard, SectionHeader } from '../components/ui/Card'
import { PageLoader } from '../components/ui/Spinner'
import { Table } from '../components/ui/Table'
import { Badge } from '../components/ui/Badge'
import type { LangSmithRun } from '../types'

const RUN_COLUMNS = [
  { key: 'run_id', header: 'Run ID', render: (r: LangSmithRun) => (
    <span className="font-mono text-xs text-slate-500 truncate block max-w-24">{r.run_id.slice(0, 12)}…</span>
  )},
  { key: 'query_snippet', header: 'Query', render: (r: LangSmithRun) => (
    <span className="text-slate-700 text-sm truncate block max-w-48">{r.query_snippet ?? '—'}</span>
  )},
  { key: 'status', header: 'Status', render: (r: LangSmithRun) => (
    <Badge variant={r.status === 'success' ? 'low' : r.status === 'error' ? 'critical' : 'default'}>
      {r.status}
    </Badge>
  )},
  { key: 'latency_ms', header: 'Latency', render: (r: LangSmithRun) => (
    <span className="font-mono text-sm">{r.latency_ms != null ? `${(r.latency_ms / 1000).toFixed(1)}s` : '—'}</span>
  )},
  { key: 'total_tokens', header: 'Tokens', render: (r: LangSmithRun) => (
    <span className="font-mono text-sm">{r.total_tokens?.toLocaleString() ?? '—'}</span>
  )},
]

export default function Observability() {
  const { data: metrics, isLoading } = useQuery({ queryKey: ['obs-metrics'], queryFn: observabilityApi.metrics, refetchInterval: 60_000 })
  const { data: runs = [] } = useQuery({ queryKey: ['ls-runs'], queryFn: () => observabilityApi.runs(30) })
  const { data: evalResults = [] } = useQuery({ queryKey: ['eval-results'], queryFn: () => evaluationApi.results(0, 10), refetchInterval: 60_000 })

  if (isLoading) return <PageLoader label="Loading observatory…" />

  // Radar chart data — average DeepEval scores across recent evaluations
  const avgMetrics = (evalResults as any[]).reduce(
    (acc, r) => {
      if (r.answer_relevancy != null)  acc.ar    += r.answer_relevancy
      if (r.faithfulness != null)      acc.fa    += r.faithfulness
      if (r.contextual_recall != null) acc.cr    += r.contextual_recall
      acc.count++
      return acc
    },
    { ar: 0, fa: 0, cr: 0, count: 0 }
  )
  const n = avgMetrics.count || 1
  const radarData = [
    { metric: 'Answer Relevancy',  score: +(avgMetrics.ar / n).toFixed(3) },
    { metric: 'Faithfulness',      score: +(avgMetrics.fa / n).toFixed(3) },
    { metric: 'Contextual Recall', score: +(avgMetrics.cr / n).toFixed(3) },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      <p className="text-slate-500 text-sm">Understanding how the AI makes decisions</p>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title="Avg Thinking Time" value={`${((metrics?.avg_latency_ms ?? 0) / 1000).toFixed(1)}s`} icon={<Clock size={18}/>} />
        <KPICard title="Quality Score" value={`${((metrics?.avg_evaluation_score ?? 0) * 10).toFixed(0)}%`} icon={<Zap size={18}/>} />
        <KPICard title="Queries Today" value={metrics?.total_queries_today ?? 0} icon={<Activity size={18}/>} />
        <KPICard title="AI Cost Today" value={`$${(metrics?.estimated_cost_today_usd ?? 0).toFixed(3)}`} icon={<DollarSign size={18}/>} />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <SectionHeader title="Agent Response Times" subtitle="Average milliseconds per agent" />
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={metrics?.per_agent_stats ?? []} margin={{ left: -20 }}>
              <XAxis dataKey="agent_name" tick={{ fontSize: 11 }} tickFormatter={(v) => v.replace('_', ' ').slice(0, 8)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => [`${v.toFixed(0)}ms`, 'Avg Latency']} />
              <Bar dataKey="avg_latency_ms" fill="#1E6FD9" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <SectionHeader title="Query Volume (7 days)" />
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={metrics?.queries_over_time ?? []} margin={{ left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d) => d.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="count" stroke="#1E6FD9" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* LangSmith runs */}
      <Card padding="none">
        <div className="p-5 border-b border-slate-100">
          <SectionHeader title="Recent AI Decisions" subtitle="LangSmith trace log" />
        </div>
        <Table columns={RUN_COLUMNS as any} data={runs as any[]} emptyMessage="No LangSmith runs available — check LANGCHAIN_API_KEY." />
      </Card>

      {/* ── Fix 4: Evaluation quality section ── */}
      <Card>
        <div className="pb-4 border-b border-slate-100 mb-5">
          <SectionHeader
            title="Recommendation Quality"
            subtitle="DeepEval RAG metrics — averaged across recent evaluations"
          />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Radar chart */}
          <div>
            <p className="text-xs font-medium text-slate-500 mb-3 uppercase tracking-wider">RAG Quality Metrics</p>
            <ResponsiveContainer width="100%" height={220}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="#e2e8f0" />
                <PolarAngleAxis dataKey="metric" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis angle={30} domain={[0, 1]} tick={{ fontSize: 9 }} />
                <Radar name="Score" dataKey="score" stroke="#1E6FD9" fill="#1E6FD9" fillOpacity={0.2} />
                <Tooltip formatter={(v: number) => [v.toFixed(2), 'Score']} />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          {/* LLM Judge verdict table */}
          <div>
            <p className="text-xs font-medium text-slate-500 mb-3 uppercase tracking-wider">LLM Judge Verdicts (recent 10)</p>
            <div className="space-y-2">
              {(evalResults as any[]).slice(0, 5).map((r: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-slate-50">
                  <span className="text-xs text-slate-500 font-mono truncate max-w-32">
                    {r.session_id?.slice(0, 8)}…
                  </span>
                  <div className="flex items-center gap-3">
                    {r.answer_relevancy != null && (
                      <span className="text-xs text-slate-500">
                        Rel: <strong>{r.answer_relevancy?.toFixed(2)}</strong>
                      </span>
                    )}
                    <Badge variant={
                      r.judge_verdict === 'APPROVED' ? 'low' :
                      r.judge_verdict === 'REJECTED' ? 'critical' : 'medium'
                    }>
                      {r.judge_verdict ?? '—'}
                    </Badge>
                  </div>
                </div>
              ))}
              {(evalResults as any[]).length === 0 && (
                <p className="text-slate-400 text-sm text-center py-6">
                  No evaluation results yet — run a query first.
                </p>
              )}
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}
