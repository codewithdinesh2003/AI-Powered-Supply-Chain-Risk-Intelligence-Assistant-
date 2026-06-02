import { useQuery } from '@tanstack/react-query'
import { Activity, Clock, DollarSign, Zap } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid } from 'recharts'
import { observabilityApi } from '../api/client'
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

  if (isLoading) return <PageLoader label="Loading observatory…" />

  return (
    <div className="space-y-6 animate-fade-in">
      <p className="text-slate-500 text-sm">Understanding how the AI makes decisions</p>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title="Avg Thinking Time" value={`${((metrics?.avg_latency_ms ?? 0) / 1000).toFixed(1)}s`} icon={<Clock size={18}/>} />
        <KPICard title="Quality Score" value={`${((metrics?.avg_evaluation_score ?? 0) * 100).toFixed(0)}%`} icon={<Zap size={18}/>} />
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
    </div>
  )
}
