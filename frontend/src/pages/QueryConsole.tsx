import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp, Search, Terminal, Zap } from 'lucide-react'
import { Card } from '../components/ui/Card'
import { Badge, PriorityBadge, VerdictBadge } from '../components/ui/Badge'
import { InlineLoader } from '../components/ui/Spinner'
import { AgentPipelinePanel } from '../components/agent-flow/AgentPipelinePanel'
import { createQueryStream, api } from '../api/client'
import { useStore, type PipelineLogEntry } from '../store/useStore'
import { clsx } from 'clsx'

// ── Bug Fix 4: Rotating hints (replaces preset pills) ────────────────────────

const HINTS = [
  'Which SKUs are at risk of stockout right now?',
  'Supplier 5 has critical defect rates — analyze the risk',
  '36 products failed inspection — who is responsible?',
  'Compare lead times across Kolkata and Mumbai suppliers',
  'Haircare stockouts and failed inspections — priority action plan',
  'Give me a complete risk assessment of our entire supply chain',
]

// ── Feedback bar ──────────────────────────────────────────────────────────────

function FeedbackBar({ sessionId }: { sessionId: string }) {
  const [submitted, setSubmitted] = useState<boolean | null>(null)

  const submit = async (helpful: boolean) => {
    try {
      await api.post(`/query/sessions/${sessionId}/feedback`, {
        rating: helpful ? 5 : 1,
        helpful,
        comment: '',
      })
      setSubmitted(helpful)
    } catch { /* non-fatal */ }
  }

  if (submitted !== null) {
    return (
      <p className="text-xs text-slate-400 text-center mt-4 pt-4 border-t border-slate-100">
        {submitted ? '👍 Thanks for the feedback!' : '👎 Feedback noted — we\'ll improve.'}
      </p>
    )
  }

  return (
    <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between">
      <p className="text-sm text-slate-500">Was this analysis helpful?</p>
      <div className="flex items-center gap-3">
        <button onClick={() => submit(true)}
          className="text-slate-400 hover:text-green-600 transition-colors text-lg">👍</button>
        <button onClick={() => submit(false)}
          className="text-slate-400 hover:text-red-500 transition-colors text-lg">👎</button>
      </div>
    </div>
  )
}

// ── Results tab system ────────────────────────────────────────────────────────

type ResultTab = 'recommendations' | 'risk_analysis' | 'retrieved' | 'evaluation'

function ResultTabs({
  result,
  fromCache,
  sessionId,
}: {
  result: NonNullable<ReturnType<typeof useStore>['currentResult']>
  fromCache: boolean
  sessionId: string
}) {
  const [tab, setTab] = useState<ResultTab>('recommendations')

  const TABS: { id: ResultTab; label: string }[] = [
    { id: 'recommendations', label: 'Recommendations' },
    { id: 'risk_analysis',   label: 'Risk Analysis' },
    { id: 'retrieved',       label: 'Retrieved Incidents' },
    { id: 'evaluation',      label: 'Evaluation' },
  ]

  return (
    <div className="space-y-4">
      {/* Executive summary bar */}
      {result.final_response && (
        <div className="flex items-start justify-between gap-4 p-4 bg-blue-50 border border-blue-200 rounded-xl">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold text-blue-700 uppercase tracking-wider">Executive Summary</span>
              {fromCache && (
                <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200 font-medium">
                  <Zap size={10} /> Cached
                </span>
              )}
            </div>
            <p className="text-slate-700 text-sm leading-relaxed">{result.final_response}</p>
          </div>
          {result.risk_score != null && (
            <div className="shrink-0 text-center">
              <div className={clsx('text-3xl font-bold font-data',
                result.risk_score >= 75 ? 'text-red-600' :
                result.risk_score >= 50 ? 'text-orange-500' :
                result.risk_score >= 25 ? 'text-amber-500' : 'text-green-600')}>
                {Math.round(result.risk_score)}
              </div>
              <div className="text-slate-400 text-xs">/100</div>
            </div>
          )}
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={clsx('px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
              tab === t.id ? 'border-[#1E6FD9] text-[#1E6FD9]' : 'border-transparent text-slate-500 hover:text-slate-700'
            )}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        {/* ── Recommendations ── */}
        {tab === 'recommendations' && (
          <motion.div key="rec" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            {result.recommendations.length === 0 ? (
              <p className="text-slate-400 text-sm text-center py-8">No recommendations generated.</p>
            ) : (
              <div className="space-y-3">
                {result.recommendations.map((rec, i) => (
                  <div key={rec.id ?? i} className="border border-slate-200 rounded-xl p-4 hover:border-slate-300 transition-colors">
                    <div className="flex items-start gap-3">
                      <PriorityBadge priority={rec.priority} />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-slate-800">{rec.action}</p>
                        <p className="text-slate-600 text-sm mt-1">{rec.rationale}</p>
                        <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-xs text-slate-500">
                          <span><strong className="text-slate-600">Timeline:</strong> {rec.timeline}</span>
                          <span><strong className="text-slate-600">Impact:</strong> {rec.expected_impact}</span>
                          <span><strong className="text-slate-600">Team:</strong> {rec.responsible_team}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <FeedbackBar sessionId={sessionId} />
          </motion.div>
        )}

        {/* ── Risk Analysis ── */}
        {tab === 'risk_analysis' && (
          <motion.div key="risk" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="space-y-3">
            {result.risk_score != null && (
              <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-xl border border-slate-200">
                <span className="text-slate-600 text-sm font-medium">Overall Risk Score</span>
                <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                  <div className={clsx('h-full rounded-full transition-all',
                    result.risk_score >= 75 ? 'bg-red-500' :
                    result.risk_score >= 50 ? 'bg-orange-400' :
                    result.risk_score >= 25 ? 'bg-amber-400' : 'bg-green-500')}
                    style={{ width: `${result.risk_score}%` }} />
                </div>
                <span className="font-mono font-bold text-slate-800 text-sm w-12 text-right">
                  {Math.round(result.risk_score)}/100
                </span>
              </div>
            )}
            <p className="text-slate-400 text-sm text-center py-4">
              Detailed per-agent analysis available in the pipeline logs above.
            </p>
          </motion.div>
        )}

        {/* ── Bug Fix 5: Retrieved Incidents ── */}
        {tab === 'retrieved' && (
          <motion.div key="ret" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            {(!result.retrieved_incidents || result.retrieved_incidents.length === 0) ? (
              <p className="text-slate-400 text-sm text-center py-8">No retrieved incidents available.</p>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-slate-500 mb-3">
                  {result.retrieved_incidents.length} documents retrieved and used as context
                </p>
                {result.retrieved_incidents.map((doc: any, i: number) => (
                  <div key={i} className="border border-slate-200 rounded-lg p-3 hover:border-slate-300 transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-mono text-slate-500 mb-1">
                          {doc.metadata?.incident_code ?? `DOC-${i + 1}`}
                        </p>
                        <p className="text-sm text-slate-700 leading-relaxed line-clamp-3">{doc.text}</p>
                        <div className="flex gap-3 mt-2 text-xs text-slate-400">
                          {doc.metadata?.severity && (
                            <span>Severity: <strong className="capitalize">{doc.metadata.severity}</strong></span>
                          )}
                          {doc.metadata?.supplier_name && (
                            <span>Supplier: <strong>{doc.metadata.supplier_name}</strong></span>
                          )}
                          {doc.metadata?.warehouse_location && (
                            <span>Location: <strong>{doc.metadata.warehouse_location}</strong></span>
                          )}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="text-xs font-mono font-bold text-[#1E6FD9]">
                          {doc.score != null ? doc.score.toFixed(3) : '—'}
                        </div>
                        <div className="text-xs text-slate-400">score</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}

        {/* ── Evaluation ── */}
        {tab === 'evaluation' && (
          <motion.div key="eval" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            {!result.evaluation_scores ? (
              <p className="text-slate-400 text-sm text-center py-8">Evaluation not available.</p>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-3 flex-wrap p-4 bg-slate-50 rounded-xl border border-slate-200">
                  {result.evaluation_scores.verdict && (
                    <VerdictBadge verdict={result.evaluation_scores.verdict} />
                  )}
                  {result.evaluation_scores.overall_score != null && (
                    <span className="font-mono text-slate-700 font-semibold">
                      {(result.evaluation_scores.overall_score as number).toFixed(1)} / 10
                    </span>
                  )}
                </div>
                {result.evaluation_scores.reasoning && (
                  <p className="text-slate-600 text-sm leading-relaxed">
                    {result.evaluation_scores.reasoning as string}
                  </p>
                )}
                {(result.evaluation_scores as any).improvement_suggestions?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">Improvement suggestions</p>
                    <ul className="space-y-1">
                      {((result.evaluation_scores as any).improvement_suggestions as string[]).map((s, i) => (
                        <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                          <span className="text-slate-400 mt-0.5">•</span>{s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Query input panel ─────────────────────────────────────────────────────────

function QueryPanel({ onSubmit, loading }: { onSubmit: (q: string) => void; loading: boolean }) {
  const [query, setQuery]       = useState('')
  const [showFilters, setShowFilters] = useState(false)
  // Bug Fix 4: rotating hints
  const [hintIdx, setHintIdx]   = useState(0)

  useEffect(() => {
    const id = setInterval(() => setHintIdx((i) => (i + 1) % HINTS.length), 4000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="space-y-4">
      <label className="block text-sm font-medium text-slate-700">
        Describe a supply chain risk situation
      </label>

      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        rows={4}
        placeholder="e.g. Supplier 5 defect rates are critical in Bangalore and Kolkata..."
        className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#1E6FD9] text-slate-800 placeholder-slate-400"
      />

      {/* Bug Fix 4: Rotating hint (replaces preset pills) */}
      <p
        className="text-xs text-slate-400 cursor-pointer hover:text-slate-600 transition-colors duration-300 -mt-1"
        onClick={() => setQuery(HINTS[hintIdx])}
        title="Click to fill"
      >
        Try: <span className="italic">{HINTS[hintIdx]}</span>
      </p>

      <button
        onClick={() => setShowFilters(!showFilters)}
        className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 transition-colors"
      >
        <Search size={14} />
        Metadata filters
        {showFilters ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {showFilters && (
        <div className="grid grid-cols-2 gap-3 p-4 bg-slate-50 rounded-xl border border-slate-200">
          {[['Supplier ID', 'supplier_id'], ['Severity', 'severity'], ['Category', 'category'], ['Warehouse', 'warehouse']].map(([label, key]) => (
            <div key={key}>
              <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-[#1E6FD9]"
                placeholder={`Filter by ${label.toLowerCase()}`}
              />
            </div>
          ))}
        </div>
      )}

      {/* Fix 4: Strong blue with glow on hover */}
      <button
        onClick={() => query.trim() && onSubmit(query.trim())}
        disabled={loading || !query.trim()}
        className="w-full font-semibold py-3 rounded-xl transition-all flex items-center justify-center gap-2 text-white disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ background: '#1E6FD9' }}
        onMouseEnter={(e) => {
          if (!loading) {
            e.currentTarget.style.background  = '#1558B0'
            e.currentTarget.style.boxShadow   = '0 0 12px rgba(30,111,217,0.4)'
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = '#1E6FD9'
          e.currentTarget.style.boxShadow  = 'none'
        }}
      >
        {loading ? <><InlineLoader /> Analyzing…</> : <><Terminal size={16} /> Analyze Risk</>}
      </button>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function QueryConsole() {
  const [fromCache, setFromCache]     = useState(false)
  const [sessionId,  setSessionId]    = useState('')

  const {
    queryStatus,
    currentResult,
    setQueryStatus,
    setCurrentResult,
    resetPipeline,
    setPipelineStatus,
    setPipelineAgentStatus,
    addPipelineLog,
  } = useStore()

  const handleSubmit = useCallback((query: string) => {
    resetPipeline()
    setFromCache(false)
    setSessionId('')
    setQueryStatus('streaming')
    setPipelineStatus('running')

    const stop = createQueryStream(
      { query },
      (raw) => {
        /* existing handler below */
        const event = raw as {
          type: string; agent: string; data: Record<string, unknown>
          timestamp: string; tokens_used?: number; total_elapsed_ms?: number
        }
        const ts = event.timestamp
          ? new Date(event.timestamp).toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
          : ''
        const log = (type: PipelineLogEntry['type'], text: string) =>
          addPipelineLog(event.agent, { type, text, ts })

        switch (event.type) {
          case 'agent_started':
            setPipelineAgentStatus(event.agent, 'running')
            log('info', (event.data?.message as string) || 'Agent started')
            break
          case 'agent_log':
            log((event.data?.log_type as PipelineLogEntry['type']) || 'info', (event.data?.message as string) || '')
            break
          case 'agent_completed': {
            const msg   = (event.data?.message as string) || 'Done'
            const tok   = event.data?.tokens_used as number | undefined
            const elaps = event.data?.elapsed_ms  as number | undefined
            log('success', `Done — ${msg}`)
            if (tok) log('info', `Tokens: ${tok}${elaps ? ` | ${elaps}ms` : ''}`)
            setPipelineAgentStatus(event.agent, 'done')
            break
          }
          case 'agent_error':
            log('error', (event.data?.error as string) || 'Agent failed')
            setPipelineAgentStatus(event.agent, 'error')
            break
          case 'final_result': {
            const d = event.data as Record<string, unknown>
            setCurrentResult({
              session_id:          sessionId,   // Bug Fix 1: real ID from X-Session-Id header
              query,
              recommendations:     (d.recommendations as any[]) ?? [],
              risk_score:          d.risk_score as number | null,
              final_response:      d.final_response as string | null,
              evaluation_scores:   d.evaluation_scores as any,
              retrieved_incidents: (d.retrieved_incidents as any[]) ?? [],
              agent_trace:         [],
              tokens_used:         event.tokens_used ?? 0,
              elapsed_ms:          event.total_elapsed_ms ?? 0,
              errors:              [],
            })
            setQueryStatus('done')
            break
          }
          case 'cache_hit':  setFromCache(true); break
          case 'pipeline_done': setPipelineStatus('complete'); break
        }
      },
      () => { setQueryStatus('done'); setPipelineStatus('complete') },
      () => { setQueryStatus('error'); setPipelineStatus('error') },
      (sid) => setSessionId(sid)   // Bug Fix 1: capture X-Session-Id from response header
    )
    return stop
  }, [resetPipeline, setQueryStatus, setPipelineStatus, setPipelineAgentStatus, addPipelineLog, setCurrentResult])

  const loading = queryStatus === 'streaming'

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Top row: input + pipeline (always visible) */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <Card><QueryPanel onSubmit={handleSubmit} loading={loading} /></Card>
        </div>
        <div className="lg:col-span-3">
          <Card><AgentPipelinePanel /></Card>
        </div>
      </div>

      {/* Results panel slides up below both when complete */}
      <AnimatePresence>
        {currentResult && (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.35, ease: 'easeOut' }}
          >
            <Card>
              <ResultTabs result={currentResult} fromCache={fromCache} sessionId={sessionId} />
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
