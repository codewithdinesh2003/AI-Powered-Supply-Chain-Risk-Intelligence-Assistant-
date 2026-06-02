import { clsx } from 'clsx'
import type { ReactNode } from 'react'

interface Column<T> {
  key: string
  header: string
  render?: (row: T) => ReactNode
  className?: string
  headerClassName?: string
}

interface TableProps<T> {
  columns: Column<T>[]
  data: T[]
  keyField?: string
  onRowClick?: (row: T) => void
  emptyMessage?: string
  className?: string
  stickyHeader?: boolean
}

export function Table<T extends Record<string, unknown>>({
  columns,
  data,
  keyField = 'id',
  onRowClick,
  emptyMessage = 'No data found.',
  className,
  stickyHeader = false,
}: TableProps<T>) {
  return (
    <div className={clsx('overflow-x-auto rounded-xl border border-slate-200 bg-white', className)}>
      <table className="w-full text-sm">
        <thead className={clsx('bg-slate-50 border-b border-slate-200', stickyHeader && 'sticky top-0 z-10')}>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={clsx(
                  'text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap',
                  col.headerClassName
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="text-center text-slate-400 py-12 text-sm">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, idx) => (
              <tr
                key={String(row[keyField] ?? idx)}
                className={clsx(
                  'transition-colors',
                  onRowClick && 'cursor-pointer hover:bg-slate-50'
                )}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={clsx('px-4 py-3 text-slate-700 whitespace-nowrap', col.className)}
                  >
                    {col.render ? col.render(row) : String(row[col.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

interface PaginationProps {
  skip: number
  limit: number
  total: number
  onSkipChange: (skip: number) => void
}

export function Pagination({ skip, limit, total, onSkipChange }: PaginationProps) {
  const page = Math.floor(skip / limit) + 1
  const totalPages = Math.ceil(total / limit)

  return (
    <div className="flex items-center justify-between px-1 mt-4 text-sm text-slate-600">
      <span>
        Showing {skip + 1}–{Math.min(skip + limit, total)} of {total}
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onSkipChange(Math.max(0, skip - limit))}
          disabled={skip === 0}
          className="px-3 py-1.5 border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50 transition-colors"
        >
          Previous
        </button>
        <span className="px-3 py-1.5 bg-slate-100 rounded-lg font-mono">
          {page} / {totalPages}
        </span>
        <button
          onClick={() => onSkipChange(skip + limit)}
          disabled={skip + limit >= total}
          className="px-3 py-1.5 border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50 transition-colors"
        >
          Next
        </button>
      </div>
    </div>
  )
}
