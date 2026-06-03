import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Building2, Package, TrendingUp, Upload } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import { dashboardApi, suppliersApi } from '../api/client'
import { Card, KPICard, SectionHeader } from '../components/ui/Card'
import { SeverityBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/Spinner'
import { Table } from '../components/ui/Table'
import type { AlertItem } from '../types'
import { formatDistanceToNow } from 'date-fns'

const SHIPMENT_COLORS = ['#10B981', '#3B82F6', '#F59E0B', '#EF4444', '#8B5CF6', '#6B7280']

function RiskMeter({ score }: { score: number }) {
  const color = score >= 75 ? '#EF4444' : score >= 50 ? '#F97316' : score >= 25 ? '#F59E0B' : '#10B981'
  return (
    <div className="mt-2">
      <div className="flex justify-between text-xs text-slate-500 mb-1">
        <span>LOW</span><span>CRITICAL</span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${score}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}

const ALERT_COLUMNS = [
  { key: 'incident_code', header: 'Code', className: 'font-mono text-xs' },
  { key: 'title', header: 'Incident', className: 'max-w-xs truncate', render: (r: AlertItem) => (
    <span className="text-slate-700 truncate block max-w-xs" title={r.title}>{r.title}</span>
  )},
  { key: 'severity', header: 'Severity', render: (r: AlertItem) => <SeverityBadge severity={r.severity} /> },
  { key: 'category', header: 'Category', render: (r: AlertItem) => (
    <span className="capitalize text-slate-600">{r.category}</span>
  )},
  { key: 'occurred_at', header: 'When', render: (r: AlertItem) => (
    <span className="text-slate-500 text-xs">
      {r.occurred_at ? formatDistanceToNow(new Date(r.occurred_at), { addSuffix: true }) : '—'}
    </span>
  )},
]

export default function Dashboard() {
  const navigate = useNavigate()
  const { data: kpis, isLoading } = useQuery({
    queryKey: ['dashboard-kpis'],
    queryFn: dashboardApi.kpis,
    refetchInterval: 60_000,
  })
  const { data: alerts = [] } = useQuery({
    queryKey: ['dashboard-alerts'],
    queryFn: () => dashboardApi.alerts(10),
    refetchInterval: 30_000,
  })
  const { data: suppliers = [] } = useQuery({
    queryKey: ['suppliers-chart'],
    queryFn: () => suppliersApi.list({ limit: 5 }),
  })

  if (isLoading) return <PageLoader label="Loading dashboard…" />

  const bySeverity = kpis?.active_incidents.by_severity ?? {}

  // Chart data
  const supplierChartData = (suppliers as any[]).slice(0, 5).map((s: any) => ({
    name: s.name,
    reliability_score: s.reliability_score ?? 0,
  }))
  const shipmentDistribution: Record<string, number> = (kpis as any)?.shipment_status_distribution ?? {}
  const shipmentChartData = Object.entries(shipmentDistribution).map(([k, v]) => ({
    name: k, value: v as number,
  }))

  return (
    <div className="space-y-6 animate-fade-in">
      {/* ── Page header with Upload shortcut ── */}
      <div className="flex items-center justify-end">
        <button
          onClick={() => navigate('/data-sources')}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-lg text-slate-600 hover:text-accent-blue hover:border-accent-blue text-sm font-medium transition-colors shadow-sm"
        >
          <Upload size={15} />
          Upload CSV
        </button>
      </div>

      {/* ── KPI Row ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Overall Risk Score"
          value={kpis?.overall_risk_score?.toFixed(0) ?? '—'}
          subtitle="Composite risk index"
          valueColor={
            (kpis?.overall_risk_score ?? 0) >= 75 ? 'text-red-600' :
            (kpis?.overall_risk_score ?? 0) >= 50 ? 'text-orange-500' :
            (kpis?.overall_risk_score ?? 0) >= 25 ? 'text-amber-500' : 'text-green-600'
          }
          icon={<TrendingUp size={18} />}
        >
          <RiskMeter score={kpis?.overall_risk_score ?? 0} />
        </KPICard>

        <KPICard
          title="Active Incidents"
          value={kpis?.active_incidents.total ?? '—'}
          subtitle={`${bySeverity['critical'] ?? 0} critical, ${bySeverity['high'] ?? 0} high`}
          icon={<AlertTriangle size={18} />}
          valueColor={(bySeverity['critical'] ?? 0) > 0 ? 'text-red-600' : 'text-slate-800'}
        />

        <KPICard
          title="Supplier Health"
          value={`${kpis?.supplier_health.pct_healthy ?? 0}%`}
          subtitle={`Avg reliability: ${kpis?.supplier_health.avg_reliability_score?.toFixed(1) ?? '—'}/100`}
          icon={<Building2 size={18} />}
          valueColor={(kpis?.supplier_health.pct_healthy ?? 100) < 60 ? 'text-red-600' : 'text-green-600'}
        />

        <KPICard
          title="Shipment On-Time Rate"
          value={`${kpis?.shipment_on_time_rate ?? 0}%`}
          subtitle={`Based on ${(kpis as any)?.shipment_records_analyzed ?? 0} shipment records`}
          icon={<Package size={18} />}
          valueColor={(kpis?.shipment_on_time_rate ?? 100) < 70 ? 'text-orange-500' : 'text-green-600'}
        />
      </div>

      {/* ── Charts row: Supplier Reliability + Shipment Status ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <SectionHeader title="Supplier Reliability" subtitle="Score by supplier (0–100)" />
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={supplierChartData} margin={{ left: -20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} tickFormatter={(v) => v.split(' ').slice(-1)[0]} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => [`${v.toFixed(0)}/100`, 'Reliability']} />
              <Bar dataKey="reliability_score" radius={[4, 4, 0, 0]} fill="#1E6FD9" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <SectionHeader title="Shipment Status" subtitle="Distribution across all records" />
          {shipmentChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={shipmentChartData} cx="50%" cy="50%"
                  innerRadius={55} outerRadius={80} paddingAngle={3} dataKey="value">
                  {shipmentChartData.map((_, i) => (
                    <Cell key={i} fill={SHIPMENT_COLORS[i % SHIPMENT_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number, name: string) => [v, name]} />
                <Legend iconSize={10} iconType="circle"
                  formatter={(v) => <span style={{ fontSize: 11 }}>{v}</span>} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-slate-400 text-sm text-center py-12">No shipment data yet.</p>
          )}
        </Card>
      </div>

      {/* ── Alert feed ── */}
      <Card padding="none">
        <div className="p-5 border-b border-slate-100">
          <SectionHeader
            title="Active Risk Alerts"
            subtitle="Open and in-progress incidents by severity"
          />
        </div>
        <Table
          columns={ALERT_COLUMNS as any}
          data={alerts as any[]}
          emptyMessage="No active alerts — supply chain looks healthy."
        />
      </Card>

      {/* ── Recent queries ── */}
      {kpis?.recent_sessions && kpis.recent_sessions.length > 0 && (
        <Card>
          <SectionHeader title="Recent AI Analyses" />
          <div className="space-y-2">
            {kpis.recent_sessions.map((s) => (
              <div key={s.id} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                <p className="text-slate-700 text-sm truncate flex-1 mr-4">{s.query_text}</p>
                <div className="flex items-center gap-3 shrink-0">
                  {s.risk_score != null && (
                    <span className="font-mono text-xs text-slate-500">score {s.risk_score.toFixed(0)}</span>
                  )}
                  <span className="text-slate-400 text-xs">{formatDistanceToNow(new Date(s.created_at), { addSuffix: true })}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
