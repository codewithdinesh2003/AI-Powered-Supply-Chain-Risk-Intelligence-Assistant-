import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type {
  AgentTraceEvent,
  QueryResult,
  QuerySessionSummary,
  User,
} from '../types'

// ── Pipeline agent state (used by AgentPipelinePanel) ────────────────────────

export type PipelineAgentStatus = 'idle' | 'running' | 'done' | 'error'

export interface PipelineLogEntry {
  type: 'info' | 'success' | 'warn' | 'error'
  text: string
  ts: string
}

export interface PipelineAgentState {
  status: PipelineAgentStatus
  logs: PipelineLogEntry[]
}

export type PipelineStatus = 'idle' | 'running' | 'complete' | 'error'

const PIPELINE_AGENT_NAMES = [
  'retrieval',
  'supplier_risk',
  'shipment_analysis',
  'inventory_intel',
  'recommendation',
  'evaluator',
] as const

function initialPipelineAgents(): Record<string, PipelineAgentState> {
  return Object.fromEntries(
    PIPELINE_AGENT_NAMES.map((name) => [name, { status: 'idle' as const, logs: [] }])
  )
}

// ── Store shape ───────────────────────────────────────────────────────────────

interface StoreState {
  // ── Auth ──────────────────────────────────────────────────────────────
  user: User | null
  accessToken: string | null
  setUser: (user: User | null) => void
  setAccessToken: (token: string | null) => void
  logout: () => void

  // ── Query streaming ────────────────────────────────────────────────────
  queryStatus: 'idle' | 'streaming' | 'done' | 'error'
  currentQuery: string
  streamEvents: AgentTraceEvent[]
  currentResult: QueryResult | null

  setQueryStatus: (status: StoreState['queryStatus']) => void
  setCurrentQuery: (q: string) => void
  pushStreamEvent: (event: AgentTraceEvent) => void
  setCurrentResult: (result: QueryResult | null) => void

  // ── Pipeline visualization (AgentPipelinePanel) ────────────────────────
  pipelineAgents: Record<string, PipelineAgentState>
  pipelineStatus: PipelineStatus
  pipelineElapsedMs: number

  setPipelineAgentStatus: (agent: string, status: PipelineAgentStatus) => void
  addPipelineLog: (agent: string, log: PipelineLogEntry) => void
  setPipelineStatus: (status: PipelineStatus) => void
  setPipelineElapsed: (ms: number) => void
  resetPipeline: () => void

  // ── Query history ──────────────────────────────────────────────────────
  queryHistory: QuerySessionSummary[]
  setQueryHistory: (sessions: QuerySessionSummary[]) => void
  prependHistory: (session: QuerySessionSummary) => void

  // ── UI state ───────────────────────────────────────────────────────────
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  activeFilters: Record<string, string>
  setFilter: (key: string, value: string) => void
  clearFilters: () => void
}

// ── Store implementation ──────────────────────────────────────────────────────

export const useStore = create<StoreState>()(
  persist(
    (set) => ({
      // ── Auth ────────────────────────────────────────────────────────────
      user: null,
      accessToken: null,
      setUser: (user) => set({ user }),
      setAccessToken: (token) => set({ accessToken: token }),
      logout: () => set({ user: null, accessToken: null }),

      // ── Query streaming ──────────────────────────────────────────────────
      queryStatus: 'idle',
      currentQuery: '',
      streamEvents: [],
      currentResult: null,

      setQueryStatus: (queryStatus) => set({ queryStatus }),
      setCurrentQuery: (currentQuery) => set({ currentQuery }),
      pushStreamEvent: (event) =>
        set((s) => ({ streamEvents: [...s.streamEvents, event] })),
      setCurrentResult: (currentResult) => set({ currentResult }),

      // ── Pipeline visualization ───────────────────────────────────────────
      pipelineAgents: initialPipelineAgents(),
      pipelineStatus: 'idle',
      pipelineElapsedMs: 0,

      setPipelineAgentStatus: (agent, status) =>
        set((s) => ({
          pipelineAgents: {
            ...s.pipelineAgents,
            [agent]: { ...s.pipelineAgents[agent], status },
          },
        })),

      addPipelineLog: (agent, log) =>
        set((s) => {
          const prev = s.pipelineAgents[agent]
          if (!prev) return s
          return {
            pipelineAgents: {
              ...s.pipelineAgents,
              [agent]: { ...prev, logs: [...prev.logs, log] },
            },
          }
        }),

      setPipelineStatus: (pipelineStatus) => set({ pipelineStatus }),
      setPipelineElapsed: (pipelineElapsedMs) => set({ pipelineElapsedMs }),

      resetPipeline: () =>
        set({
          pipelineAgents:   initialPipelineAgents(),
          pipelineStatus:   'idle',
          pipelineElapsedMs: 0,
          queryStatus:      'idle',
          streamEvents:     [],
          currentResult:    null,
        }),

      // ── Query history ────────────────────────────────────────────────────
      queryHistory: [],
      setQueryHistory: (queryHistory) => set({ queryHistory }),
      prependHistory: (session) =>
        set((s) => ({ queryHistory: [session, ...s.queryHistory].slice(0, 50) })),

      // ── UI ────────────────────────────────────────────────────────────────
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      activeFilters: {},
      setFilter: (key, value) =>
        set((s) => ({ activeFilters: { ...s.activeFilters, [key]: value } })),
      clearFilters: () => set({ activeFilters: {} }),
    }),
    {
      name: 'scm-intel-store',
      partialize: (s) => ({
        user:             s.user,
        accessToken:      s.accessToken,
        sidebarCollapsed: s.sidebarCollapsed,
        queryHistory:     s.queryHistory,
      }),
    }
  )
)
