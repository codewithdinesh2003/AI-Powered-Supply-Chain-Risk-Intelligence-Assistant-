import { useState, useCallback } from 'react'
import { Terminal, ChevronDown, ChevronUp, Search } from 'lucide-react'
import { Card } from '../components/ui/Card'
import { Badge, PriorityBadge, VerdictBadge } from '../components/ui/Badge'
import { InlineLoader } from '../components/ui/Spinner'
import { createQueryStream } from '../api/client'
import { useStore } from '../store/useStore'
import type { AgentTraceEvent, QueryResult } from '../types'

const PRESET_QUERIES = [
  'Supplier delays for critical components in Asia-Pacific',
  'Port congestion impacting shipment schedules',
  'Inventory approaching stockout threshold',
  'Transportation cost spike detected on key routes',
  'Demand surge bottleneck affecting fulfillment',
]

// ── Query Input Panel ─────────────────────────────────────────────────────────
function QueryPanel({ onSubmit, loading }: { onSubmit: (q: string) => void; loading: boolean }) {
  const [query, setQuery] = useState('')
  const [showFilters, setShowFilters] = useState(false)

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-2">Describe a supply chain risk situation</label>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={4}
          placeholder="e.g. Supplier delays for critical components in Asia-Pacific region…"
          className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-accent-blue text-slate-800 placeholder-slate-400"
        />
      </div>

      {/* Preset pills */}
      <div className="flex flex-wrap gap-2">
        {PRESET_QUERIES.map((q) => (
          <button
            key={q}
            onClick={() => setQuery(q)}
            className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-blue-50 hover:text-accent-blue border border-slate-200 hover:border-accent-blue rounded-full transition-colors text-slate-600"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Filters toggle */}
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
                className="w-full border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-accent-blue"
                placeholder={`Filter by ${label.toLowerCase()}`}
              />
            </div>
          ))}
        </div>
      )}

      <button
        onClick={() => query.trim() && onSubmit(query.trim())}
        disabled={loading || !query.trim()}
        className="w-full bg-accent-blue hover:bg-accent-blue-light disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition-colors flex items-center justify-center gap-2"
      >
        {loading ? <><InlineLoader /> Analyzing…</> : <><Terminal size={16} /> Analyze Risk</>}
      </button>
    </div>
  )
}

// ── Agent Status Node (mini) ──────────────────────────────────────────────────
function AgentStatusRow({ name, label, status }: { name: string; label: string; status: string }) {
  const icons: Record<string, string> = { idle: '○', running: '⟳', completed: '✓', error: '✕' }
  const colors: Record<string, string> = {
    idle: 'text-slate-400',
    running: 'text-accent-blue animate-spin',
    completed: 'text-green-600',
    error: 'text-red-600',
  }
  return (
    <div className="flex items-center gap-3 py-2 border-b border-slate-50 last:border-0">
      <span className={`text-lg font-mono ${colors[status] ?? colors.idle}`}>{icons[status] ?? '○'}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-700">{label}</p>
      </div>
      {status === 'running' && <InlineLoader />}
      {status === 'completed' && <span className="text-xs text-green-600 font-medium">Done</span>}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function QueryConsole() {
  const { queryStatus, agentStates, currentResult, setQueryStatus, updateAgentState, setCurrentResult, pushStreamEvent, resetQuery } = useStore()

  const handleSubmit = useCallback((query: string) => {
    resetQuery()
    setQueryStatus('streaming')
    updateAgentState('query', { status: 'completed' })
    updateAgentState('retrieval', { status: 'running' })

    const stop = createQueryStream(
      { query },
      (event) => {
        const e = event as AgentTraceEvent
        pushStreamEvent(e)

        if (e.type === 'agent_started') {
          updateAgentState(e.agent, { status: 'running' })
        } else if (e.type === 'agent_completed') {
          updateAgentState(e.agent, { status: 'completed', output: e.data, elapsed_ms: e.elapsed_ms, tokens: e.tokens_used })
        } else if (e.type === 'agent_error') {
          updateAgentState(e.agent, { status: 'error' })
        } else if (e.type === 'final_result') {
          const d = e.data as any
          setCurrentResult({
            session_id: '',
            query,
            recommendations: d.recommendations ?? [],
            risk_score: d.risk_score,
            final_response: d.final_response,
            evaluation_scores: d.evaluation_scores,
            retrieved_incidents: [],
            agent_trace: [],
            tokens_used: e.tokens_used,
            elapsed_ms: e.total_elapsed_ms ?? 0,
            errors: [],
          })
          setQueryStatus('done')
        }
      },
      () => setQueryStatus('done'),
      () => setQueryStatus('error')
    )
    return stop
  }, [])

  const AGENT_LIST = [
    { key: 'retrieval',         label: 'Hybrid Retrieval' },
    { key: 'supplier_risk',     label: 'Supplier Risk Agent' },
    { key: 'shipment_analysis', label: 'Shipment Analysis Agent' },
    { key: 'inventory_intel',   label: 'Inventory Intelligence' },
    { key: 'recommendation',    label: 'Recommendation Agent' },
    { key: 'evaluator',         label: 'Evaluator' },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* ── Left: Input ── */}
        <div className="lg:col-span-2">
          <Card>
            <QueryPanel onSubmit={handleSubmit} loading={queryStatus === 'streaming'} />
          </Card>
        </div>

        {/* ── Right: Agent pipeline ── */}
        <div className="lg:col-span-3">
          <Card>
            <h3 className="font-semibold text-slate-800 mb-4 flex items-center gap-2">
              <Terminal size={16} className="text-accent-blue" />
              Agent Pipeline
            </h3>
            <div className="space-y-0">
              {AGENT_LIST.map(({ key, label }) => (
                <AgentStatusRow
                  key={key}
                  name={key}
                  label={label}
                  status={agentStates[key as keyof typeof agentStates]?.status ?? 'idle'}
                />
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* ── Results ── */}
      {currentResult && (
        <div className="space-y-4 animate-slide-in">
          {/* Executive summary */}
          {currentResult.final_response && (
            <Card className="border-l-4 border-accent-blue">
              <h3 className="font-semibold text-slate-800 mb-2">Executive Summary</h3>
              <p className="text-slate-700">{currentResult.final_response}</p>
              {currentResult.risk_score != null && (
                <div className="mt-3 flex items-center gap-2">
                  <span className="text-slate-500 text-sm">Overall Risk Score:</span>
                  <span className="text-2xl font-bold font-data text-red-600">{currentResult.risk_score.toFixed(0)}</span>
                  <span className="text-slate-400 text-sm">/100</span>
                </div>
              )}
            </Card>
          )}

          {/* Recommendations */}
          {currentResult.recommendations.length > 0 && (
            <Card>
              <h3 className="font-semibold text-slate-800 mb-4">Mitigation Recommendations</h3>
              <div className="space-y-3">
                {currentResult.recommendations.map((rec, i) => (
                  <div key={rec.id ?? i} className="border border-slate-200 rounded-xl p-4">
                    <div className="flex items-start gap-3">
                      <PriorityBadge priority={rec.priority} />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-slate-800">{rec.action}</p>
                        <p className="text-slate-600 text-sm mt-1">{rec.rationale}</p>
                        <div className="flex flex-wrap gap-4 mt-2 text-xs text-slate-500">
                          <span><strong>Timeline:</strong> {rec.timeline}</span>
                          <span><strong>Impact:</strong> {rec.expected_impact}</span>
                          <span><strong>Team:</strong> {rec.responsible_team}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Evaluation scores */}
          {currentResult.evaluation_scores && (
            <Card>
              <h3 className="font-semibold text-slate-800 mb-3">Quality Evaluation</h3>
              <div className="flex items-center gap-4 flex-wrap">
                {currentResult.evaluation_scores.verdict && (
                  <VerdictBadge verdict={currentResult.evaluation_scores.verdict} />
                )}
                {currentResult.evaluation_scores.overall_score != null && (
                  <span className="font-mono text-slate-600 text-sm">
                    Score: {currentResult.evaluation_scores.overall_score.toFixed(1)}/10
                  </span>
                )}
                {currentResult.evaluation_scores.reasoning && (
                  <p className="text-slate-500 text-sm w-full mt-1">{currentResult.evaluation_scores.reasoning}</p>
                )}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
