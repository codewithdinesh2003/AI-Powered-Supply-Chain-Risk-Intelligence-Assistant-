import { NavLink, useLocation } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  Building2,
  Database,
  GitBranch,
  Home,
  Settings,
  Terminal,
  Zap,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { useStore } from '../../store/useStore'
import { dashboardApi } from '../../api/client'

const NAV_ITEMS = [
  { to: '/',              label: 'Dashboard',    icon: Home,          exact: true },
  { to: '/query',         label: 'Query Console',icon: Terminal,      exact: false },
  { to: '/incidents',     label: 'Incidents',    icon: AlertTriangle, exact: false },
  { to: '/suppliers',     label: 'Suppliers',    icon: Building2,     exact: false },
  { to: '/data-sources',  label: 'Data Sources', icon: Database,      exact: false },
  { to: '/observability', label: 'Observability',icon: Activity,      exact: false },
  { to: '/architecture',  label: 'Architecture', icon: GitBranch,     exact: false },
  { to: '/settings',      label: 'Settings',     icon: Settings,      exact: false },
]

function RiskBadge({ score }: { score: number }) {
  const label = score >= 75 ? 'CRITICAL' : score >= 50 ? 'HIGH' : score >= 25 ? 'MEDIUM' : 'LOW'
  const cls   = score >= 75 ? 'bg-red-500' : score >= 50 ? 'bg-orange-500' : score >= 25 ? 'bg-amber-400' : 'bg-green-500'
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold text-white', cls)}>
      {label}
    </span>
  )
}

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, user } = useStore((s) => ({
    sidebarCollapsed: s.sidebarCollapsed,
    toggleSidebar: s.toggleSidebar,
    user: s.user,
  }))
  const location = useLocation()

  // Fix 8: use dashboard KPI score (TanStack Query caches; no extra network request
  // if Dashboard page has already fetched with the same ['dashboard-kpis'] key)
  const { data: kpis } = useQuery({
    queryKey: ['dashboard-kpis'],
    queryFn: dashboardApi.kpis,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const riskScore = kpis?.overall_risk_score ?? 0

  return (
    <aside
      className={clsx(
        'flex flex-col h-screen bg-navy-900 border-r border-navy-700 transition-all duration-200 shrink-0',
        sidebarCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* ── Logo ── */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-navy-700">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-accent-blue shrink-0">
          <Zap size={16} className="text-white" />
        </div>
        {!sidebarCollapsed && (
          <div>
            <span className="text-white font-semibold tracking-widest text-sm font-mono">
              SCM<span className="text-accent-blue">·</span>INTEL
            </span>
            <p className="text-navy-400 text-xs">Risk Intelligence</p>
          </div>
        )}
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto py-4 scrollbar-thin">
        <ul className="space-y-0.5 px-2">
          {NAV_ITEMS.map(({ to, label, icon: Icon, exact }) => {
            const isActive = exact ? location.pathname === to : location.pathname.startsWith(to)
            return (
              <li key={to}>
                <NavLink
                  to={to}
                  className={clsx(
                    'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
                    isActive
                      ? 'bg-accent-blue text-white shadow-lg'
                      : 'text-slate-400 hover:text-white hover:bg-navy-700'
                  )}
                >
                  <Icon size={18} className="shrink-0" />
                  {!sidebarCollapsed && <span>{label}</span>}
                </NavLink>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* ── Footer: user + risk score ── */}
      <div className="border-t border-navy-700 p-4 space-y-3">
        {!sidebarCollapsed && (
          <>
            <div className="flex items-center justify-between">
              <span className="text-navy-400 text-xs uppercase tracking-wider font-mono">System Risk</span>
              <RiskBadge score={riskScore} />
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-accent-blue-dim flex items-center justify-center text-white text-xs font-bold shrink-0">
                {user?.full_name?.[0] ?? 'U'}
              </div>
              <div className="min-w-0">
                <p className="text-white text-sm truncate">{user?.full_name ?? 'Guest'}</p>
                <p className="text-navy-400 text-xs capitalize">{user?.role ?? 'analyst'}</p>
              </div>
            </div>
          </>
        )}
        <button
          onClick={toggleSidebar}
          className="w-full flex justify-center text-navy-400 hover:text-white transition-colors"
          title={sidebarCollapsed ? 'Expand' : 'Collapse'}
        >
          <span className="text-xs">{sidebarCollapsed ? '›' : '‹'}</span>
        </button>
      </div>
    </aside>
  )
}
