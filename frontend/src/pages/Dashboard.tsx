import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Building2, Package, TrendingUp } from 'lucide-react'
import { dashboardApi } from '../api/client'
import { Card, KPICard, SectionHeader } from '../components/ui/Card'
import { SeverityBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/Spinner'
import { Table } from '../components/ui/Table'
import type { AlertItem } from '../types'
import { formatDistanceToNow } from 'date-fns'

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

  if (isLoading) return <PageLoader label="Loading dashboard…" />

  const bySeverity = kpis?.active_incidents.by_severity ?? {}

  return (
    <div className="space-y-6 animate-fade-in">
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
          subtitle={`${kpis?.ai_queries.today ?? 0} AI queries today`}
          icon={<Package size={18} />}
          valueColor={(kpis?.shipment_on_time_rate ?? 100) < 70 ? 'text-orange-500' : 'text-green-600'}
        />
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
