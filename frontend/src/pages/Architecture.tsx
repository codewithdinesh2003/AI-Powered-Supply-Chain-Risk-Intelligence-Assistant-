import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'

const TECH_STACK = [
  { name: 'FastAPI', role: 'Backend API', color: 'bg-green-100 text-green-700' },
  { name: 'LangGraph', role: 'Agent Orchestration', color: 'bg-blue-100 text-blue-700' },
  { name: 'LangSmith', role: 'Observability', color: 'bg-purple-100 text-purple-700' },
  { name: 'ChromaDB', role: 'Vector Store', color: 'bg-orange-100 text-orange-700' },
  { name: 'MySQL', role: 'Structured Data', color: 'bg-blue-100 text-blue-700' },
  { name: 'OpenAI GPT-4o', role: 'LLM Agents', color: 'bg-slate-100 text-slate-700' },
  { name: 'BM25 + CrossEncoder', role: 'Hybrid Retrieval', color: 'bg-amber-100 text-amber-700' },
  { name: 'DeepEval', role: 'Quality Evaluation', color: 'bg-pink-100 text-pink-700' },
  { name: 'React + Vite', role: 'Frontend', color: 'bg-cyan-100 text-cyan-700' },
  { name: 'React Flow', role: 'Agent Visualization', color: 'bg-indigo-100 text-indigo-700' },
]

const DESIGN_DECISIONS = [
  {
    title: 'Why ChromaDB?',
    body: 'Persistent, local, production-ready vector database with no external service dependency. Supports cosine similarity search, metadata filtering, and upsert operations — ideal for supply chain document retrieval at this scale.',
  },
  {
    title: 'Why Hybrid Search (BM25 + Semantic)?',
    body: 'Semantic search excels at conceptual similarity ("supplier reliability issues") but misses exact keyword matches ("SUP-003", "INC-00042"). BM25 catches precise identifiers that embeddings dilute. Reciprocal Rank Fusion (RRF) merges both without requiring score normalization.',
  },
  {
    title: 'Why LangGraph?',
    body: 'Explicit, typed agent state makes the pipeline inspectable and debuggable. Conditional edges enable routing logic. astream() yields node-level events enabling real-time SSE streaming to the frontend. Every node is individually traceable in LangSmith.',
  },
  {
    title: 'Why CrossEncoder Reranker?',
    body: 'Bi-encoder embeddings encode query and document independently — they miss fine-grained relevance signals. CrossEncoder sees the (query, document) pair jointly, dramatically improving precision. Applied to the top-20 fused candidates keeps latency acceptable (~100ms).',
  },
  {
    title: 'Token Optimization Strategy',
    body: 'tiktoken counts tokens before each LLM call. Context is compressed at 80% of the model limit using byte-pair-encoding-aware truncation (not character-level). Supplier summaries are pre-computed at ingestion time to reduce per-query token usage.',
  },
]

function ArchNode({ label, sub, color = 'bg-blue-50 border-blue-200' }: { label: string; sub?: string; color?: string }) {
  return (
    <div className={`border ${color} rounded-xl px-4 py-3 text-center shadow-sm min-w-28`}>
      <p className="font-semibold text-slate-800 text-sm">{label}</p>
      {sub && <p className="text-slate-500 text-xs mt-0.5">{sub}</p>}
    </div>
  )
}

function Arrow({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5 mx-2">
      <div className="w-12 h-0.5 bg-slate-300" />
      {label && <span className="text-slate-400 text-xs">{label}</span>}
    </div>
  )
}

export default function Architecture() {
  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      {/* Pipeline diagram */}
      <Card>
        <h2 className="font-semibold text-slate-800 text-base mb-6">System Architecture</h2>

        <div className="overflow-x-auto pb-2">
          {/* Row 1: Data → Ingestion → Stores */}
          <div className="flex items-center mb-6">
            <ArchNode label="CSV Data" sub="supply chain events" color="bg-slate-50 border-slate-200" />
            <Arrow label="ingest" />
            <ArchNode label="Chunker + Embedder" sub="OpenAI text-embedding-3-small" />
            <div className="flex flex-col gap-2 ml-4">
              <Arrow />
              <Arrow />
            </div>
            <div className="flex flex-col gap-2">
              <ArchNode label="ChromaDB" sub="vector store" color="bg-orange-50 border-orange-200" />
              <ArchNode label="MySQL" sub="structured data" color="bg-blue-50 border-blue-200" />
              <ArchNode label="BM25 Index" sub="keyword index" color="bg-amber-50 border-amber-200" />
            </div>
          </div>

          {/* Row 2: Query → Retrieval → Agents */}
          <div className="flex items-start">
            <ArchNode label="User Query" sub="natural language" color="bg-green-50 border-green-200" />
            <Arrow label="embed" />
            <div className="flex flex-col gap-1">
              <ArchNode label="Hybrid Retrieval" sub="BM25 + Semantic + RRF + Rerank" color="bg-purple-50 border-purple-200" />
            </div>
            <Arrow />
            <div className="flex flex-col gap-2">
              <ArchNode label="Supplier Risk" sub="GPT-4o" color="bg-red-50 border-red-200" />
              <ArchNode label="Shipment Analysis" sub="GPT-4o" color="bg-orange-50 border-orange-200" />
              <ArchNode label="Inventory Intel" sub="GPT-4o" color="bg-amber-50 border-amber-200" />
            </div>
            <Arrow />
            <ArchNode label="Recommendation" sub="GPT-4o" color="bg-blue-50 border-blue-200" />
            <Arrow />
            <ArchNode label="Evaluator" sub="LLM Judge + DeepEval" color="bg-green-50 border-green-200" />
            <Arrow label="SSE" />
            <ArchNode label="React UI" sub="live agent flow" color="bg-slate-50 border-slate-200" />
          </div>
        </div>

        <p className="text-slate-500 text-xs mt-4 italic">
          LangSmith traces every agent call → full observability in the Observatory page.
        </p>
      </Card>

      {/* Design decisions */}
      <Card>
        <h2 className="font-semibold text-slate-800 text-base mb-4">Design Decisions</h2>
        <div className="space-y-4">
          {DESIGN_DECISIONS.map((d) => (
            <div key={d.title} className="border-b border-slate-100 pb-4 last:border-0 last:pb-0">
              <h3 className="font-medium text-slate-800 mb-1">{d.title}</h3>
              <p className="text-slate-600 text-sm leading-relaxed">{d.body}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* Tech stack grid */}
      <Card>
        <h2 className="font-semibold text-slate-800 text-base mb-4">Technology Stack</h2>
        <div className="flex flex-wrap gap-3">
          {TECH_STACK.map(({ name, role, color }) => (
            <div key={name} className={`inline-flex flex-col items-center px-4 py-3 rounded-xl border ${color.replace('text-', 'border-').replace('-700','-200').replace('-100','').replace('bg-','border-')} bg-white shadow-sm min-w-32`}>
              <span className="font-semibold text-sm text-slate-800">{name}</span>
              <span className={`text-xs mt-0.5 ${color.split(' ')[1]}`}>{role}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
