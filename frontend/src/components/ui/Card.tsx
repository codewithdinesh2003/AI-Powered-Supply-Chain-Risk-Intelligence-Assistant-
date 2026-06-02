import { clsx } from 'clsx'
import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  padding?: 'none' | 'sm' | 'md' | 'lg'
  hover?: boolean
}

export function Card({ children, className, padding = 'md', hover = false }: CardProps) {
  const padMap = { none: '', sm: 'p-3', md: 'p-5', lg: 'p-6' }
  return (
    <div
      className={clsx(
        'bg-white rounded-xl border border-slate-200 shadow-card',
        hover && 'transition-shadow hover:shadow-card-hover cursor-pointer',
        padMap[padding],
        className
      )}
    >
      {children}
    </div>
  )
}

interface KPICardProps {
  title: string
  value: string | number
  subtitle?: string
  icon?: ReactNode
  trend?: 'up' | 'down' | 'neutral'
  trendValue?: string
  valueColor?: string
  children?: ReactNode
}

export function KPICard({ title, value, subtitle, icon, trend, trendValue, valueColor, children }: KPICardProps) {
  const trendColor = trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : 'text-slate-500'
  const trendArrow = trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <p className="text-slate-500 text-sm font-medium">{title}</p>
        {icon && <div className="text-slate-400">{icon}</div>}
      </div>
      <div>
        <p className={clsx('text-3xl font-bold font-data', valueColor ?? 'text-slate-800')}>
          {value}
        </p>
        {subtitle && <p className="text-slate-500 text-sm mt-0.5">{subtitle}</p>}
      </div>
      {trendValue && (
        <p className={clsx('text-sm font-medium', trendColor)}>
          {trendArrow} {trendValue}
        </p>
      )}
      {children}
    </Card>
  )
}

interface SectionHeaderProps {
  title: string
  subtitle?: string
  action?: ReactNode
}

export function SectionHeader({ title, subtitle, action }: SectionHeaderProps) {
  return (
    <div className="flex items-start justify-between mb-4">
      <div>
        <h2 className="text-slate-800 font-semibold text-base">{title}</h2>
        {subtitle && <p className="text-slate-500 text-sm mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}
