import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { suppliersApi } from '../api/client'
import { Card, SectionHeader } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Table } from '../components/ui/Table'
import { PageLoader } from '../components/ui/Spinner'
import type { Supplier } from '../types'

function ReliabilityBar({ score }: { score: number }) {
  const color = score >= 80 ? 'bg-green-500' : score >= 60 ? 'bg-amber-400' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden w-20">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="font-mono text-xs text-slate-600 w-8 text-right">{score.toFixed(0)}</span>
    </div>
  )
}

const COLUMNS = [
  { key: 'supplier_id', header: 'ID', className: 'font-mono text-xs text-slate-500' },
  { key: 'name', header: 'Supplier Name', render: (r: Supplier) => (
    <span className="font-medium text-slate-800">{r.name}</span>
  )},
  { key: 'region', header: 'Region', render: (r: Supplier) => (
    <span className="text-slate-600 text-sm">{r.region ?? '—'}</span>
  )},
  { key: 'category', header: 'Category' },
  { key: 'reliability_score', header: 'Reliability', render: (r: Supplier) => (
    r.reliability_score != null ? <ReliabilityBar score={r.reliability_score} /> : <span className="text-slate-400">—</span>
  )},
  { key: 'avg_delay_days', header: 'Avg Delay', render: (r: Supplier) => (
    <span className={`font-mono text-sm ${(r.avg_delay_days ?? 0) > 7 ? 'text-red-600 font-semibold' : 'text-slate-600'}`}>
      {r.avg_delay_days != null ? `${r.avg_delay_days.toFixed(1)}d` : '—'}
    </span>
  )},
  { key: 'active_orders', header: 'Orders', className: 'font-mono text-center text-sm' },
  { key: 'risk_level', header: 'Risk', render: (r: Supplier) => {
    const map: Record<string, string> = { critical: 'critical', high: 'high', medium: 'medium', low: 'low' }
    return <Badge variant={map[r.risk_level] as any}>{r.risk_level}</Badge>
  }},
]

export default function Suppliers() {
  const [search, setSearch] = useState('')
  const [riskLevel, setRiskLevel] = useState('')

  const { data: suppliers = [], isLoading } = useQuery({
    queryKey: ['suppliers', search, riskLevel],
    queryFn: () => suppliersApi.list({
      ...(search && { search }),
      ...(riskLevel && { risk_level: riskLevel }),
    }),
  })

  const { data: stats } = useQuery({ queryKey: ['supplier-stats'], queryFn: suppliersApi.stats })

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Summary */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card padding="sm" className="text-center">
            <p className="text-2xl font-bold font-data">{(stats as any).total_suppliers}</p>
            <p className="text-slate-500 text-xs mt-1">Total Suppliers</p>
          </Card>
          {(['critical','high','medium','low'] as const).map((r) => (
            <Card key={r} padding="sm" className="text-center">
              <p className="text-2xl font-bold font-data">{(stats as any).by_risk_level?.[r] ?? 0}</p>
              <Badge variant={r}>{r}</Badge>
            </Card>
          ))}
        </div>
      )}

      {/* Table */}
      <Card padding="none">
        <div className="p-4 border-b border-slate-100 flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search suppliers…"
              className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-blue"
            />
          </div>
          <select
            value={riskLevel}
            onChange={(e) => setRiskLevel(e.target.value)}
            className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent-blue"
          >
            <option value="">All risk levels</option>
            {['critical','high','medium','low'].map((r) => (
              <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
            ))}
          </select>
        </div>
        {isLoading ? <PageLoader /> : (
          <Table columns={COLUMNS as any} data={suppliers as any[]} emptyMessage="No suppliers found." />
        )}
      </Card>
    </div>
  )
}
