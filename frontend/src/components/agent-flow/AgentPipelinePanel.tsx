import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { clsx } from 'clsx'
import { useStore, type PipelineAgentState, type PipelineLogEntry } from '../../store/useStore'

// ── Agent metadata ────────────────────────────────────────────────────────────

const AGENT_META: Record<string, { label: string; subtitle: string }> = {
  retrieval:         { label: 'Hybrid Retrieval',    subtitle: 'BM25 + Semantic + Rerank' },
  supplier_risk:     { label: 'Supplier Risk Agent',  subtitle: 'Delivery risk analysis' },
  shipment_analysis: { label: 'Shipment Analysis',    subtitle: 'Delay prediction' },
  inventory_intel:   { label: 'Inventory Intel',      subtitle: 'Stockout detection' },
  recommendation:    { label: 'Recommendation Agent', subtitle: 'Mitigation strategies' },
  evaluator:         { label: 'Quality Evaluator',    subtitle: 'Output assessment' },
}

// ── Status styling ────────────────────────────────────────────────────────────

const STATUS_BOX: Record<string, string> = {
  idle:    'border-slate-200 opacity-60',
  running: 'border-[#378ADD] pipeline-running-box',
  done:    'border-[#639922]',
  error:   'border-[#E24B4A]',
}
const STATUS_DOT: Record<string, string> = {
  idle:    'bg-[#888780]',
  running: 'bg-[#378ADD] pipeline-dot-pulse',
  done:    'bg-[#639922]',
  error:   'bg-[#E24B4A]',
}
const STATUS_BADGE: Record<string, string> = {
  idle:    'bg-slate-100 text-slate-500',
  running: 'bg-blue-100 text-[#378ADD]',
  done:    'bg-green-100 text-[#639922]',
  error:   'bg-red-100 text-[#E24B4A]',
}
const STATUS_LABEL: Record<string, string> = {
  idle:    'idle',
  running: 'running...',
  done:    'done',
  error:   'error',
}
const LOG_COLOR: Record<string, string> = {
  info:    'text-slate-500',
  success: 'text-[#639922]',
  warn:    'text-amber-600',
  error:   'text-[#E24B4A]',
}
const LOG_PREFIX: Record<string, string> = {
  info:    '→',
  success: '✓',
  warn:    '⚠',
  error:   '✕',
}

// ── Log line ──────────────────────────────────────────────────────────────────

function LogLine({ log }: { log: PipelineLogEntry }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={clsx('flex gap-2 font-mono text-[11px] leading-[1.5]', LOG_COLOR[log.type] ?? 'text-slate-500')}
    >
      <span className="shrink-0 w-16 text-slate-400">{log.ts}</span>
      <span className="shrink-0">{LOG_PREFIX[log.type] ?? '→'}</span>
      <span>{log.text}</span>
    </motion.div>
  )
}

// ── Agent box ─────────────────────────────────────────────────────────────────

function AgentBox({ name, state }: { name: string; state: PipelineAgentState }) {
  const meta      = AGENT_META[name] ?? { label: name, subtitle: '' }
  const { status, logs } = state
  const logsRef   = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (logsRef.current) logsRef.current.scrollTop = logsRef.current.scrollHeight
  }, [logs.length])

  return (
    <div className={clsx('rounded-xl border-[1.5px] bg-white px-4 py-3 transition-all duration-300', STATUS_BOX[status])}>
      <div className="flex items-center gap-3">
        <div className={clsx('w-2.5 h-2.5 rounded-full shrink-0', STATUS_DOT[status])} />
        <div className="flex-1 min-w-0">
          <p className="text-slate-800 font-semibold text-sm leading-tight">{meta.label}</p>
          <p className="text-slate-400 text-xs">{meta.subtitle}</p>
        </div>
        <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-full', STATUS_BADGE[status])}>
          {STATUS_LABEL[status]}
        </span>
      </div>

      <AnimatePresence initial={false}>
        {(status === 'running' || status === 'done' || status === 'error') && logs.length > 0 && (
          <motion.div
            key="logs"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div
              ref={logsRef}
              className="mt-3 pt-3 border-t border-slate-100 space-y-0.5 max-h-[120px] overflow-y-auto scrollbar-thin"
            >
              {logs.map((log, i) => <LogLine key={i} log={log} />)}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Fix 3: Branch connector (pure CSS/HTML — no SVG, no React Flow) ──────────

function BranchDown({ active }: { active: boolean }) {
  return (
    <div className="flex justify-center h-5">
      <div className={clsx('w-[2px]', active ? 'bg-[#B5D4F4]' : 'bg-slate-200')} />
    </div>
  )
}

function FanOutConnector({ active }: { active: boolean }) {
  const line = active ? 'bg-[#B5D4F4]' : 'bg-slate-200'
  return (
    <div className="flex flex-col items-center">
      {/* Vertical drop from retrieval */}
      <div className={clsx('w-[2px] h-4', line)} />
      {/* Horizontal bar spanning roughly the 3 columns */}
      <div className="relative w-[75%] h-[2px]" style={{ background: active ? '#B5D4F4' : '#E2E8F0' }}>
        {/* Left drop */}
        <div className={clsx('absolute left-0 bottom-0 w-[2px] h-4', line)} />
        {/* Center drop */}
        <div className={clsx('absolute left-1/2 -translate-x-1/2 bottom-0 w-[2px] h-4', line)} />
        {/* Right drop */}
        <div className={clsx('absolute right-0 bottom-0 w-[2px] h-4', line)} />
      </div>
    </div>
  )
}

function FanInConnector({ active }: { active: boolean }) {
  const line = active ? 'bg-[#B5D4F4]' : 'bg-slate-200'
  return (
    <div className="flex flex-col items-center">
      {/* Horizontal bar with three rises */}
      <div className="relative w-[75%] h-[2px]" style={{ background: active ? '#B5D4F4' : '#E2E8F0' }}>
        {/* Left rise */}
        <div className={clsx('absolute left-0 top-0 w-[2px] h-4 -translate-y-full', line)} />
        {/* Center rise */}
        <div className={clsx('absolute left-1/2 -translate-x-1/2 top-0 w-[2px] h-4 -translate-y-full', line)} />
        {/* Right rise */}
        <div className={clsx('absolute right-0 top-0 w-[2px] h-4 -translate-y-full', line)} />
      </div>
      {/* Center drop to recommendation */}
      <div className={clsx('w-[2px] h-4', line)} />
    </div>
  )
}

function Connector({ active, animated }: { active: boolean; animated: boolean }) {
  return (
    <div className="relative flex justify-center h-7">
      <div className={clsx('w-[2px] h-full rounded-full', active ? 'bg-[#B5D4F4]' : 'bg-slate-200')} />
      {animated && <div className="connector-dot absolute left-1/2 -translate-x-1/2" />}
    </div>
  )
}

// ── Fix 5: Elapsed timer that starts from first click ────────────────────────
// Receives startedAt timestamp so it measures wall-clock from submit, not mount

function ElapsedTimer({ running, stopped }: { running: boolean; stopped: boolean }) {
  const [ms, setMs] = useState(0)
  const startRef = useRef<number | null>(null)
  const frameRef = useRef<number>(0)

  useEffect(() => {
    if (running) {
      startRef.current = startRef.current ?? performance.now()
      const tick = () => {
        setMs(Math.round(performance.now() - startRef.current!))
        frameRef.current = requestAnimationFrame(tick)
      }
      frameRef.current = requestAnimationFrame(tick)
      return () => cancelAnimationFrame(frameRef.current)
    } else if (stopped) {
      cancelAnimationFrame(frameRef.current)
    } else {
      // reset
      startRef.current = null
      setMs(0)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, stopped])

  if (ms === 0 && !running && !stopped) return null
  return <span className="font-mono text-sm text-slate-600">{(ms / 1000).toFixed(1)}s</span>
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function AgentPipelinePanel() {
  const { pipelineAgents, pipelineStatus, resetPipeline } = useStore((s) => ({
    pipelineAgents: s.pipelineAgents,
    pipelineStatus: s.pipelineStatus,
    resetPipeline:  s.resetPipeline,
  }))

  const isRunning  = pipelineStatus === 'running'
  const isComplete = pipelineStatus === 'complete'
  const isError    = pipelineStatus === 'error'

  const ag = (name: string) => pipelineAgents[name] ?? { status: 'idle', logs: [] }

  const parallelActive =
    ag('supplier_risk').status !== 'idle' ||
    ag('shipment_analysis').status !== 'idle' ||
    ag('inventory_intel').status !== 'idle'

  const mergeActive =
    ag('supplier_risk').status    === 'done' ||
    ag('shipment_analysis').status === 'done' ||
    ag('inventory_intel').status  === 'done' ||
    ag('recommendation').status   === 'running'

  const statusText: Record<string, string> = {
    idle:     'idle',
    running:  'executing...',
    complete: 'complete',
    error:    'error',
  }

  return (
    <div className="flex flex-col select-none">
      {/* ── Fix 5: Header with timer always visible when active ── */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-slate-700 text-sm">Agent pipeline</span>
          <span className={clsx(
            'text-xs px-2 py-0.5 rounded-full font-medium',
            isRunning  ? 'bg-blue-100 text-[#378ADD]' :
            isComplete ? 'bg-green-100 text-[#639922]' :
            isError    ? 'bg-red-100 text-[#E24B4A]' :
            'bg-slate-100 text-slate-500'
          )}>
            {statusText[pipelineStatus]}
          </span>
          {/* Timer shows next to status label — always visible while running/done */}
          <ElapsedTimer running={isRunning} stopped={isComplete || isError} />
        </div>
        {pipelineStatus !== 'idle' && (
          <button
            onClick={resetPipeline}
            className="text-xs text-slate-400 hover:text-slate-600 border border-slate-200 rounded px-2 py-0.5 transition-colors"
          >
            Reset
          </button>
        )}
      </div>

      {/* Row 1 — Retrieval */}
      <AgentBox name="retrieval" state={ag('retrieval')} />

      {/* Fix 3: Pure CSS fan-out connector */}
      <FanOutConnector active={ag('retrieval').status === 'done' || parallelActive} />

      {/* Row 2 — 3 parallel agents */}
      <div className="grid grid-cols-3 gap-3">
        <AgentBox name="supplier_risk"     state={ag('supplier_risk')} />
        <AgentBox name="shipment_analysis" state={ag('shipment_analysis')} />
        <AgentBox name="inventory_intel"   state={ag('inventory_intel')} />
      </div>

      {/* Fix 3: Pure CSS fan-in connector */}
      <FanInConnector active={mergeActive} />

      {/* Row 3 — Recommendation */}
      <AgentBox name="recommendation" state={ag('recommendation')} />

      {/* Simple connector */}
      <Connector
        active={ag('recommendation').status === 'done' || ag('evaluator').status === 'running'}
        animated={ag('recommendation').status === 'done' && ag('evaluator').status === 'running'}
      />

      {/* Row 4 — Evaluator */}
      <AgentBox name="evaluator" state={ag('evaluator')} />
    </div>
  )
}
