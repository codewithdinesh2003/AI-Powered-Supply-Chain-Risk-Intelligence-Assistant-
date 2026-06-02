import { clsx } from 'clsx'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
  label?: string
}

const SIZE_MAP = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-10 h-10' }

export function Spinner({ size = 'md', className, label }: SpinnerProps) {
  return (
    <div className={clsx('flex flex-col items-center gap-2', className)}>
      <svg
        className={clsx('animate-spin text-accent-blue', SIZE_MAP[size])}
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      {label && <span className="text-slate-500 text-sm">{label}</span>}
    </div>
  )
}

export function PageLoader({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center h-64 gap-3">
      <Spinner size="lg" />
      <p className="text-slate-500 text-sm">{label}</p>
    </div>
  )
}

export function InlineLoader() {
  return (
    <span className="inline-flex gap-1 items-center">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 bg-accent-blue rounded-full animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  )
}
