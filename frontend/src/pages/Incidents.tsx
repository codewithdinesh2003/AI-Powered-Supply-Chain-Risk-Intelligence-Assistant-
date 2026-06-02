import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Filter } from 'lucide-react'
import { incidentsApi } from '../api/client'
import { Card, SectionHeader } from '../components/ui/Card'
import { SeverityBadge, Badge } from '../components/ui/Badge'
import { Table, Pagination } from '../components/ui/Table'
import { PageLoader } from '../components/ui/Spinner'
import type { Incident } from '../types'
import { formatDistanceToNow } from 'date-fns'

const COLUMNS = [
  { key: 'incident_code', header: 'Code', className: 'font-mono text-xs text-slate-500' },
  { key: 'title', header: 'Title', render: (r: Incident) => (
    <span className="text-slate-800 font-medium text-sm max-w-xs truncate block" title={r.title}>{r.title}</span>
  )},
  { key: 'severity', header: 'Severity', render: (r: Incident) => <SeverityBadge severity={r.severity} /> },
  { key: 'category', header: 'Category', render: (r: Incident) => (
    <Badge variant="blue">{r.category}</Badge>
  )},
  { key: 'supplier_ref', header: 'Supplier', className: 'font-mono text-xs' },
  { key: 'delivery_delay_days', header: 'Delay', render: (r: Incident) => (
    <span className={`font-mono text-sm ${(r.delivery_delay_days ?? 0) > 7 ? 'text-red-600 font-semibold' : 'text-slate-600'}`}>
      {r.delivery_delay_days != null ? `${r.delivery_delay_days}d` : '—'}
    </span>
  )},
  { key: 'resolution_status', header: 'Status', render: (r: Incident) => {
    const map: Record<string, string> = { open: 'medium', in_progress: 'blue', resolved: 'low', closed: 'default' }
    return <Badge variant={map[r.resolution_status] as any}>{r.resolution_status.replace('_', ' ')}</Badge>
  }},
  { key: 'occurred_at', header: 'Date', render: (r: Incident) => (
    <span className="text-slate-400 text-xs">
      {r.occurred_at ? formatDistanceToNow(new Date(r.occurred_at), { addSuffix: true }) : '—'}
    </span>
  )},
]

export default function Incidents() {
  const [skip, setSkip] = useState(0)
  const [search, setSearch] = useState('')
  const [severity, setSeverity] = useState('')
  const LIMIT = 50

  const { data, isLoading, meta } = useQuery({
    queryKey: ['incidents', skip, search, severity],
    queryFn: () => incidentsApi.list({ skip, limit: LIMIT, ...(search && { search }), ...(severity && { severity }) }),
    select: (d) => d,
  }) as any

  const { data: stats } = useQuery({ queryKey: ['incident-stats'], queryFn: incidentsApi.stats })

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {(['critical','high','medium','low'] as const).map((s) => (
            <Card key={s} padding="sm" className="text-center">
              <p className="text-2xl font-bold font-data">{stats.by_severity?.[s] ?? 0}</p>
              <SeverityBadge severity={s} />
            </Card>
          ))}
        </div>
      )}

      {/* Filters + table */}
      <Card padding="none">
        <div className="p-4 border-b border-slate-100 flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(e) => { setSearch(e.target.value); setSkip(0) }}
              placeholder="Search incidents…"
              className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-blue"
            />
          </div>
          <select
            value={severity}
            onChange={(e) => { setSeverity(e.target.value); setSkip(0) }}
            className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent-blue"
          >
            <option value="">All severities</option>
            {['critical','high','medium','low'].map((s) => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>

        {isLoading ? <PageLoader /> : (
          <>
            <Table columns={COLUMNS as any} data={data ?? []} />
            <div className="p-4">
              <Pagination skip={skip} limit={LIMIT} total={stats?.total ?? (data?.length ?? 0)} onSkipChange={setSkip} />
            </div>
          </>
        )}
      </Card>
    </div>
  )
}
