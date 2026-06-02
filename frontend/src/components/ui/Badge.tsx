import { clsx } from 'clsx'
import type { Severity, RiskLevel } from '../../types'

interface BadgeProps {
  variant?: Severity | RiskLevel | 'p1' | 'p2' | 'p3' | 'default' | 'blue' | 'approved' | 'needs_revision' | 'rejected'
  children: React.ReactNode
  className?: string
  size?: 'sm' | 'md'
}

const VARIANT_CLASSES: Record<string, string> = {
  critical:       'bg-red-100 text-red-700 border border-red-200',
  high:           'bg-orange-100 text-orange-700 border border-orange-200',
  medium:         'bg-amber-100 text-amber-700 border border-amber-200',
  low:            'bg-green-100 text-green-700 border border-green-200',
  p1:             'bg-red-600 text-white',
  p2:             'bg-orange-500 text-white',
  p3:             'bg-blue-500 text-white',
  blue:           'bg-blue-100 text-blue-700 border border-blue-200',
  approved:       'bg-green-100 text-green-700 border border-green-200',
  needs_revision: 'bg-amber-100 text-amber-700 border border-amber-200',
  rejected:       'bg-red-100 text-red-700 border border-red-200',
  default:        'bg-slate-100 text-slate-600 border border-slate-200',
}

export function Badge({ variant = 'default', children, className, size = 'sm' }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center font-semibold uppercase tracking-wide rounded',
        size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-2.5 py-1',
        VARIANT_CLASSES[variant] ?? VARIANT_CLASSES.default,
        className
      )}
    >
      {children}
    </span>
  )
}

export function SeverityBadge({ severity }: { severity: string }) {
  const v = severity.toLowerCase() as Severity
  return <Badge variant={v}>{severity}</Badge>
}

export function PriorityBadge({ priority }: { priority: string }) {
  const v = priority.toLowerCase() as 'p1' | 'p2' | 'p3'
  return <Badge variant={v}>{priority}</Badge>
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const map: Record<string, string> = {
    APPROVED: 'approved',
    NEEDS_REVISION: 'needs_revision',
    REJECTED: 'rejected',
  }
  return <Badge variant={(map[verdict] ?? 'default') as 'approved'}>{verdict.replace('_', ' ')}</Badge>
}
