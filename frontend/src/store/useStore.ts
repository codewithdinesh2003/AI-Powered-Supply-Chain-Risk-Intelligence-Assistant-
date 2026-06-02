import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type {
  AgentNodeData,
  AgentStatus,
  AgentTraceEvent,
  QueryResult,
  QuerySessionSummary,
  User,
} from '../types'

// ── Agent node initial positions (mirrors React Flow layout) ───────────────

const AGENT_NAMES = [
  'query',
  'retrieval',
  'supplier_risk',
  'shipment_analysis',
  'inventory_intel',
  'recommendation',
  'evaluator',
] as const

type AgentName = typeof AGENT_NAMES[number]

export type AgentStates = Record<AgentName, AgentNodeData>

function initialAgentStates(): AgentStates {
  return {
    query:            { label: 'Query Input',                role: 'Natural language query',       status: 'idle' },
    retrieval:        { label: 'Hybrid Retrieval',           role: 'BM25 + Semantic + Rerank',     status: 'idle' },
    supplier_risk:    { label: 'Supplier Risk Agent',        role: 'Delivery risk analysis',       status: 'idle' },
    shipment_analysis:{ label: 'Shipment Analysis Agent',    role: 'Delay prediction',             status: 'idle' },
    inventory_intel:  { label: 'Inventory Intelligence',     role: 'Stockout detection',           status: 'idle' },
    recommendation:   { label: 'Recommendation Agent',       role: 'Mitigation strategies',        status: 'idle' },
    evaluator:        { label: 'Evaluator',                  role: 'Quality assessment',           status: 'idle' },
  }
}

// ── Store shape ───────────────────────────────────────────────────────────

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
  agentStates: AgentStates
  streamEvents: AgentTraceEvent[]
  currentResult: QueryResult | null

  setQueryStatus: (status: StoreState['queryStatus']) => void
  setCurrentQuery: (q: string) => void
  updateAgentState: (agent: string, patch: Partial<AgentNodeData>) => void
  pushStreamEvent: (event: AgentTraceEvent) => void
  setCurrentResult: (result: QueryResult | null) => void
  resetQuery: () => void

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

// ── Store implementation ──────────────────────────────────────────────────

export const useStore = create<StoreState>()(
  persist(
    (set, get) => ({
      // ── Auth ────────────────────────────────────────────────────────────
      user: null,
      accessToken: null,
      setUser: (user) => set({ user }),
      setAccessToken: (token) => set({ accessToken: token }),
      logout: () => set({ user: null, accessToken: null }),

      // ── Query streaming ──────────────────────────────────────────────────
      queryStatus: 'idle',
      currentQuery: '',
      agentStates: initialAgentStates(),
      streamEvents: [],
      currentResult: null,

      setQueryStatus: (queryStatus) => set({ queryStatus }),
      setCurrentQuery: (currentQuery) => set({ currentQuery }),

      updateAgentState: (agent, patch) =>
        set((state) => ({
          agentStates: {
            ...state.agentStates,
            [agent]: {
              ...state.agentStates[agent as AgentName],
              ...patch,
            },
          },
        })),

      pushStreamEvent: (event) =>
        set((state) => ({ streamEvents: [...state.streamEvents, event] })),

      setCurrentResult: (currentResult) => set({ currentResult }),

      resetQuery: () =>
        set({
          queryStatus: 'idle',
          agentStates: initialAgentStates(),
          streamEvents: [],
          currentResult: null,
        }),

      // ── Query history ────────────────────────────────────────────────────
      queryHistory: [],
      setQueryHistory: (queryHistory) => set({ queryHistory }),
      prependHistory: (session) =>
        set((state) => ({ queryHistory: [session, ...state.queryHistory].slice(0, 50) })),

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
      // Only persist auth + UI preferences — not streaming state
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        sidebarCollapsed: state.sidebarCollapsed,
        queryHistory: state.queryHistory,
      }),
    }
  )
)
