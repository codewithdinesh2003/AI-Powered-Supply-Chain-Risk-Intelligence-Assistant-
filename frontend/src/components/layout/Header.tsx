import { useLocation } from 'react-router-dom'
import { Bell, LogOut, RefreshCw } from 'lucide-react'
import { clsx } from 'clsx'
import { useStore } from '../../store/useStore'

const ROUTE_LABELS: Record<string, { title: string; subtitle: string }> = {
  '/':              { title: 'Operations Dashboard',   subtitle: 'Real-time supply chain risk overview' },
  '/query':         { title: 'Query Console',          subtitle: 'AI-powered risk analysis & recommendations' },
  '/incidents':     { title: 'Incident Management',    subtitle: 'Historical supply chain disruptions' },
  '/suppliers':     { title: 'Supplier Intelligence',  subtitle: 'Vendor risk profiles & performance' },
  '/observability': { title: 'System Observatory',     subtitle: 'AI performance & decision transparency' },
  '/architecture':  { title: 'System Architecture',    subtitle: 'How the AI intelligence pipeline works' },
  '/settings':      { title: 'Settings',               subtitle: 'Configuration & preferences' },
}

export function Header() {
  const location = useLocation()
  const { user, logout } = useStore((s) => ({ user: s.user, logout: s.logout }))

  const route = ROUTE_LABELS[location.pathname] ?? { title: 'SCM·INTEL', subtitle: '' }

  return (
    <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0">
      {/* ── Breadcrumb / title ── */}
      <div>
        <h1 className="text-slate-800 font-semibold text-base leading-tight">{route.title}</h1>
        {route.subtitle && (
          <p className="text-slate-500 text-xs mt-0.5">{route.subtitle}</p>
        )}
      </div>

      {/* ── Actions ── */}
      <div className="flex items-center gap-2">
        <span className="hidden sm:flex items-center gap-1.5 text-xs text-slate-500 font-mono bg-slate-50 border border-slate-200 rounded px-2 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block animate-pulse" />
          LIVE
        </span>

        <button
          className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors relative"
          title="Notifications"
        >
          <Bell size={16} />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-red-500 rounded-full" />
        </button>

        <button
          onClick={() => window.location.reload()}
          className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
          title="Refresh data"
        >
          <RefreshCw size={16} />
        </button>

        {user && (
          <button
            onClick={logout}
            className="flex items-center gap-2 px-3 py-1.5 text-slate-600 hover:text-red-600 hover:bg-red-50 border border-slate-200 rounded-lg text-sm transition-colors"
            title="Sign out"
          >
            <LogOut size={14} />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        )}
      </div>
    </header>
  )
}
