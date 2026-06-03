import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  CloudUpload, CheckCircle, XCircle, AlertCircle,
  LayoutDashboard, RefreshCw, Search, ScanSearch,
  Eye, Play, Database, FileText,
} from 'lucide-react'
import { clsx } from 'clsx'
import { etlApi, uploadApi, type DetectionResult, type FieldMappingSpec, type ETLJob } from '../api/client'
import { Card, SectionHeader } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { Table } from '../components/ui/Table'
import { formatDistanceToNow } from 'date-fns'

// ── Types ─────────────────────────────────────────────────────────────────────

type WizardStep = 'upload' | 'detecting' | 'review' | 'previewing' | 'running' | 'complete' | 'error'

// ── Helpers ───────────────────────────────────────────────────────────────────

function confidenceVariant(conf: number): 'low' | 'medium' | 'high' {
  if (conf >= 0.8) return 'high'
  if (conf >= 0.5) return 'medium'
  return 'low'
}

function confidenceLabel(conf: number): string {
  if (conf >= 0.8) return 'HIGH'
  if (conf >= 0.5) return 'MEDIUM'
  return 'LOW'
}

const CONFIDENCE_COLORS: Record<string, string> = {
  high:   'bg-green-100 text-green-700 border-green-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low:    'bg-red-100 text-red-700 border-red-200',
}

const ETL_STAGES = [
  'Reading file structure',
  'Matching columns',
  'Validating data types',
  'Deriving computed fields',
  'Loading to database',
]

function ProgressBar({ progress, status }: { progress: number; status: string }) {
  const color = status === 'failed' ? 'bg-red-500' : status === 'completed' ? 'bg-green-500' : 'bg-accent-blue'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-slate-500 font-mono">
        <span>{progress}%</span>
        <span>{status === 'completed' ? 'Done ✓' : status === 'failed' ? 'Failed ✗' : 'Processing…'}</span>
      </div>
      <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
        <motion.div
          className={clsx('h-full rounded-full', color)}
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.4 }}
        />
      </div>
    </div>
  )
}

// ── Step 1: Upload zone ───────────────────────────────────────────────────────

function UploadZone({ onFile }: { onFile: (f: File) => void }) {
  const [drag, setDrag] = useState(false)
  const ref = useRef<HTMLInputElement>(null)

  const onDragOver  = (e: React.DragEvent) => { e.preventDefault(); setDrag(true) }
  const onDragLeave = () => setDrag(false)
  const onDrop      = (e: React.DragEvent) => {
    e.preventDefault(); setDrag(false)
    const f = e.dataTransfer.files[0]
    if (f) onFile(f)
  }

  return (
    <div
      onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
      onClick={() => ref.current?.click()}
      className={clsx(
        'border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all',
        drag ? 'border-accent-blue bg-blue-50 scale-[1.01]' : 'border-slate-300 hover:border-accent-blue hover:bg-slate-50'
      )}
    >
      <input ref={ref} type="file" accept=".csv" className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f) }} />
      <CloudUpload size={52} className={clsx('mx-auto mb-3', drag ? 'text-accent-blue' : 'text-slate-300')} />
      <p className="font-semibold text-slate-700 text-lg">Drop your CSV here or click to browse</p>
      <p className="text-slate-400 text-sm mt-1">.csv only · max 50 MB</p>
      <div className="mt-4 inline-flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 text-xs text-blue-700">
        <Search size={14} />
        Alias matching + fuzzy search will auto-detect your column structure
      </div>
    </div>
  )
}

// ── Step 2: Mapping review table ──────────────────────────────────────────────

const CANONICAL_DESCRIPTIONS: Record<string, string> = {
  supplier_id: 'Unique supplier identifier',
  supplier_name: 'Supplier display name',
  product_type: 'Product / component category',
  sku: 'Stock Keeping Unit',
  inventory_level: 'Current stock (units)',
  order_quantity: 'Quantity ordered',
  demand_forecast: 'Forecasted demand',
  lead_time_days: 'Supplier lead time (days)',
  delivery_delay_days: 'Delivery delay vs expected',
  shipment_status: 'on_time / delayed / critical',
  shipping_carrier: 'Carrier / shipping company',
  transportation_mode: 'Road / Air / Rail / Sea',
  route: 'Shipment route',
  warehouse_location: 'Warehouse / facility',
  transportation_cost: 'Shipping cost (USD)',
  manufacturing_cost: 'Production cost (USD)',
  revenue: 'Revenue generated (USD)',
  defect_rate: 'Quality defect rate (0–1)',
  inspection_status: 'Pass / Fail / Pending',
  production_volume: 'Units produced',
  severity: 'Derived risk severity',
  risk_score: 'Derived risk score (0–100)',
  timestamp: 'Event timestamp (ISO8601)',
}

function MappingRow({
  canonicalField,
  spec,
  sourceColumns,
  onChange,
}: {
  canonicalField: string
  spec: FieldMappingSpec
  sourceColumns: string[]
  onChange: (field: string, update: Partial<FieldMappingSpec>) => void
}) {
  const cv = confidenceVariant(spec.confidence)
  const isLow    = cv === 'low'
  const isDerived = spec.transform === 'derive'

  return (
    <tr className={clsx('border-b border-slate-100', isLow && 'bg-amber-50')}>
      {/* Canonical field */}
      <td className="px-4 py-3">
        <p className="font-mono text-sm font-medium text-slate-800">{canonicalField}</p>
        <p className="text-slate-400 text-xs">{CANONICAL_DESCRIPTIONS[canonicalField] || ''}</p>
      </td>

      {/* Source column selector */}
      <td className="px-4 py-3">
        {isDerived ? (
          <span className="text-slate-400 text-sm italic">{spec.derive_formula || 'auto-derived'}</span>
        ) : (
          <select
            value={spec.source_column || ''}
            onChange={e => onChange(canonicalField, { source_column: e.target.value || null })}
            className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 w-full focus:outline-none focus:ring-2 focus:ring-accent-blue"
          >
            <option value="">— Not available —</option>
            {sourceColumns.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
      </td>

      {/* Transform */}
      <td className="px-4 py-3">
        <select
          value={spec.transform}
          onChange={e => onChange(canonicalField, { transform: e.target.value as any })}
          className="text-xs border border-slate-200 rounded px-2 py-1 focus:outline-none"
        >
          {['direct','derive','divide_by_100','negate','date_parse','slugify'].map(t =>
            <option key={t} value={t}>{t}</option>
          )}
        </select>
      </td>

      {/* Confidence + badges */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className={clsx('text-xs font-bold px-2 py-0.5 rounded border', CONFIDENCE_COLORS[cv])}>
            {confidenceLabel(spec.confidence)}
          </span>
          {isDerived && (
            <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded border border-blue-200">
              DERIVED
            </span>
          )}
          {!spec.source_column && !isDerived && (
            <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded border border-red-200">
              MISSING
            </span>
          )}
        </div>
      </td>
    </tr>
  )
}

// ── ETL Progress view ─────────────────────────────────────────────────────────

function ETLProgress({ jobId, onReset }: { jobId: string; onReset: () => void }) {
  const navigate = useNavigate()
  const { data: job } = useQuery({
    queryKey: ['etl-job', jobId],
    queryFn:  () => etlApi.jobStatus(jobId),
    refetchInterval: d => (d?.status === 'completed' || d?.status === 'failed') ? false : 2000,
  })

  if (!job) return <div className="py-12 flex justify-center"><Spinner size="lg" label="Starting ETL…" /></div>

  const done   = job.status === 'completed'
  const failed = job.status === 'failed'
  const result = job.result as any

  return (
    <div className="space-y-5">
      <ProgressBar progress={job.progress} status={job.status} />

      <p className="text-center text-slate-600 text-sm font-medium">{job.step}</p>

      {/* Stage indicators */}
      <div className="grid grid-cols-3 gap-2">
        {ETL_STAGES.map((stage, i) => {
          const threshold = (i + 1) / ETL_STAGES.length * 100
          const stageDone = job.progress >= threshold || done
          const stageActive = !stageDone && job.progress >= (i / ETL_STAGES.length * 100)
          return (
            <div key={stage} className={clsx(
              'flex items-center gap-1.5 text-xs rounded-lg px-2 py-1.5',
              stageDone ? 'text-green-700 bg-green-50' :
              stageActive ? 'text-accent-blue bg-blue-50 font-medium' : 'text-slate-400 bg-slate-50'
            )}>
              {stageDone ? <CheckCircle size={12} /> : stageActive ? <Spinner size="sm" /> :
                <div className="w-3 h-3 rounded-full border border-slate-300" />}
              {stage}
            </div>
          )
        })}
      </div>

      {/* Completion summary — Fix 5: accurate counts + distributions */}
      {done && result && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="bg-green-50 border border-green-200 rounded-xl p-5 space-y-4">
          <div className="flex items-center gap-2 text-green-700 font-semibold text-lg">
            <CheckCircle size={22} /> ETL Complete
          </div>

          {/* Row counts */}
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-white rounded-lg p-3 border border-green-200">
              <p className="text-2xl font-bold font-data text-green-700">{(result.rows_valid ?? 0).toLocaleString()}</p>
              <p className="text-slate-500 text-xs mt-0.5">Ingested successfully</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-amber-200">
              <p className="text-2xl font-bold font-data text-amber-600">{(result.rows_with_warnings ?? 0).toLocaleString()}</p>
              <p className="text-slate-500 text-xs mt-0.5">With warnings (kept)</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-slate-200">
              <p className="text-2xl font-bold font-data text-red-500">{(result.rows_failed ?? 0).toLocaleString()}</p>
              <p className="text-slate-500 text-xs mt-0.5">Skipped (unrecoverable)</p>
            </div>
          </div>

          {/* Severity distribution */}
          {result.severity_distribution && Object.keys(result.severity_distribution).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">Severity breakdown</p>
              <div className="flex flex-wrap gap-2">
                {(['critical','high','medium','low'] as const).map(sev => {
                  const count = (result.severity_distribution as Record<string, number>)[sev]
                  if (!count) return null
                  const cls: Record<string, string> = { critical: 'bg-red-100 text-red-700', high: 'bg-orange-100 text-orange-700', medium: 'bg-amber-100 text-amber-700', low: 'bg-green-100 text-green-700' }
                  return <span key={sev} className={`text-xs font-semibold px-3 py-1 rounded-full ${cls[sev]}`}>{sev}: {count.toLocaleString()}</span>
                })}
              </div>
            </div>
          )}

          {/* Shipment status distribution */}
          {result.shipment_status_distribution && Object.keys(result.shipment_status_distribution).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">Shipment status</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(result.shipment_status_distribution as Record<string, number>).map(([st, cnt]) => (
                  <span key={st} className="text-xs font-medium px-3 py-1 rounded-full bg-slate-100 text-slate-700">{st}: {cnt.toLocaleString()}</span>
                ))}
              </div>
            </div>
          )}

          {result.fields_derived?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-1">Fields derived</p>
              <div className="flex flex-wrap gap-1">
                {result.fields_derived.map((f: string) =>
                  <span key={f} className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">{f}</span>
                )}
              </div>
            </div>
          )}

          {result.warnings?.length > 0 && (
            <div className="text-amber-700 bg-amber-50 rounded-lg px-3 py-2 space-y-0.5">
              {result.warnings.slice(0, 3).map((w: string, i: number) =>
                <p key={i} className="text-xs">⚠ {w}</p>
              )}
            </div>
          )}

          <div className="flex gap-2">
            <button onClick={() => navigate('/')}
              className="flex-1 bg-green-600 hover:bg-green-700 text-white font-semibold py-2.5 rounded-xl transition-colors flex items-center justify-center gap-2 text-sm">
              <LayoutDashboard size={15} /> Go to Dashboard
            </button>
            <button onClick={onReset}
              className="px-4 py-2 border border-slate-200 rounded-xl text-slate-600 hover:bg-slate-50 text-sm transition-colors">
              Upload another
            </button>
          </div>
        </motion.div>
      )}

      {/* Failure */}
      {failed && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 space-y-1">
          <div className="flex items-center gap-2 font-semibold"><XCircle size={18} /> ETL Failed</div>
          {job.errors.map((e, i) => <p key={i} className="text-sm">{e}</p>)}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DataSources() {
  const [step, setStep]              = useState<WizardStep>('upload')
  const [file, setFile]              = useState<File | null>(null)
  const [detection, setDetection]    = useState<DetectionResult | null>(null)
  const [mapping, setMapping]        = useState<Record<string, FieldMappingSpec>>({})
  const [previewRows, setPreviewRows]= useState<Record<string, unknown>[]>([])
  const [etlJobId, setEtlJobId]      = useState<string | null>(null)
  const [companyName, setCompanyName]= useState('My Company')
  const [saveMapping, setSaveMapping]= useState(false)
  const [error, setError]            = useState<string | null>(null)

  const { data: history = [], refetch: refetchHistory } = useQuery({
    queryKey: ['upload-history'],
    queryFn: uploadApi.history,
    refetchInterval: step === 'running' ? 5000 : false,
  })

  // ── Step 1 → 2: Upload file and detect ────────────────────────────────
  const handleFile = useCallback(async (f: File) => {
    if (!f.name.endsWith('.csv')) { setError('Only .csv files accepted.'); return }
    setFile(f); setError(null); setStep('detecting')

    try {
      const result = await etlApi.detect(f)
      setDetection(result)
      setMapping(result.detected_mapping.mappings)
      setStep('review')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Detection failed.')
      setStep('error')
    }
  }, [])

  // ── Mapping change ─────────────────────────────────────────────────────
  const updateMapping = useCallback((field: string, patch: Partial<FieldMappingSpec>) => {
    setMapping(prev => ({ ...prev, [field]: { ...prev[field], ...patch } }))
  }, [])

  // ── Preview ────────────────────────────────────────────────────────────
  const handlePreview = useCallback(async () => {
    if (!detection) return
    setStep('previewing')
    try {
      const result = await etlApi.preview(detection.temp_file_id, mapping)
      setPreviewRows(result.rows)
      setStep('review')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Preview failed.')
      setStep('review')
    }
  }, [detection, mapping])

  // ── Step 3: Run ETL ────────────────────────────────────────────────────
  const handleRun = useCallback(async () => {
    if (!detection) return
    setStep('running')
    try {
      const result = await etlApi.run(
        detection.temp_file_id, mapping,
        companyName.toLowerCase().replace(/\s+/g, '-'),
        companyName, saveMapping,
      )
      setEtlJobId(result.job_id)
      refetchHistory()
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'ETL start failed.')
      setStep('error')
    }
  }, [detection, mapping, companyName, saveMapping])

  const reset = () => {
    setStep('upload'); setFile(null); setDetection(null); setMapping({})
    setPreviewRows([]); setEtlJobId(null); setError(null)
  }

  // ── Step indicator ─────────────────────────────────────────────────────
  const STEPS = ['Upload & Detect', 'Review Mapping', 'ETL & Ingest']
  const stepIdx = step === 'upload' || step === 'detecting' ? 0 :
                  step === 'review' || step === 'previewing' ? 1 : 2

  const HISTORY_COLS = [
    { key: 'filename', header: 'Filename', render: (r: any) => (
      <span className="flex items-center gap-2 text-slate-700 text-sm font-medium">
        <FileText size={14} className="text-slate-400" /> {r.filename}
      </span>
    )},
    { key: 'created_at', header: 'Uploaded', render: (r: any) => (
      <span className="text-slate-500 text-xs">{formatDistanceToNow(new Date(r.created_at), { addSuffix: true })}</span>
    )},
    { key: 'records_processed', header: 'Records', render: (r: any) => <span className="font-mono text-sm">{r.records_processed?.toLocaleString()}</span> },
    { key: 'status', header: 'Status', render: (r: any) => {
      const map: Record<string, string> = { completed: 'low', failed: 'critical', processing: 'blue', pending: 'default' }
      return <Badge variant={(map[r.status] ?? 'default') as any}>{r.status}</Badge>
    }},
  ]

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      {/* ── Step indicator ── */}
      <div className="flex items-center gap-0">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center flex-1">
            <div className={clsx('flex items-center gap-2 text-sm font-medium',
              i < stepIdx ? 'text-green-600' : i === stepIdx ? 'text-accent-blue' : 'text-slate-400')}>
              <div className={clsx('w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2',
                i < stepIdx ? 'bg-green-500 border-green-500 text-white' :
                i === stepIdx ? 'bg-accent-blue border-accent-blue text-white' :
                'border-slate-300 text-slate-400')}>
                {i < stepIdx ? '✓' : i + 1}
              </div>
              {label}
            </div>
            {i < STEPS.length - 1 && (
              <div className={clsx('flex-1 h-0.5 mx-3', i < stepIdx ? 'bg-green-400' : 'bg-slate-200')} />
            )}
          </div>
        ))}
      </div>

      {/* ── Main card ── */}
      <Card>
        <AnimatePresence mode="wait">
          {/* ── UPLOAD ── */}
          {step === 'upload' && (
            <motion.div key="upload" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <SectionHeader title="Upload Supply Chain Data"
                subtitle="Drop any CSV — alias matching and fuzzy search will map your columns to the canonical schema." />
              <UploadZone onFile={handleFile} />
              {error && (
                <div className="mt-3 flex items-center gap-2 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                  <AlertCircle size={15} /> {error}
                </div>
              )}
            </motion.div>
          )}

          {/* ── DETECTING ── */}
          {step === 'detecting' && (
            <motion.div key="detecting" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="py-16 flex flex-col items-center gap-4">
              <div className="w-14 h-14 rounded-full bg-blue-50 border-2 border-accent-blue flex items-center justify-center">
                <ScanSearch size={28} className="text-accent-blue animate-pulse" />
              </div>
              <p className="font-semibold text-slate-800 text-lg">Analyzing your data</p>
              <p className="text-slate-500 text-sm">Matching your columns to the supply chain schema…</p>
              <p className="text-slate-400 text-xs font-mono">{file?.name}</p>
            </motion.div>
          )}

          {/* ── REVIEW ── */}
          {(step === 'review' || step === 'previewing') && detection && (
            <motion.div key="review" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="space-y-5">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-slate-800">Review Column Mapping</h3>
                  <p className="text-slate-500 text-sm mt-0.5">
                    {detection.filename} · {detection.row_count?.toLocaleString()} rows detected
                  </p>
                </div>
                <button onClick={reset} className="text-slate-400 hover:text-slate-600 text-sm underline">Start over</button>
              </div>

              {detection.detected_mapping.notes && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2.5 text-blue-700 text-sm flex items-start gap-2">
                  <Search size={15} className="shrink-0 mt-0.5" />
                  {detection.detected_mapping.notes}
                </div>
              )}

              {/* Mapping table */}
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      {['Canonical Field', 'Your Column', 'Transform', 'Confidence'].map(h => (
                        <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(mapping).map(([field, spec]) => (
                      <MappingRow
                        key={field}
                        canonicalField={field}
                        spec={spec}
                        sourceColumns={detection.detected_mapping.source_columns}
                        onChange={updateMapping}
                      />
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Company + save mapping */}
              <div className="flex flex-wrap items-center gap-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
                <div className="flex-1 min-w-48">
                  <label className="block text-xs font-medium text-slate-600 mb-1">Company / Dataset name</label>
                  <input value={companyName} onChange={e => setCompanyName(e.target.value)}
                    className="w-full border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent-blue" />
                </div>
                <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                  <input type="checkbox" checked={saveMapping} onChange={e => setSaveMapping(e.target.checked)}
                    className="w-4 h-4 rounded" />
                  Save mapping for future uploads from this company
                </label>
              </div>

              {/* Preview rows */}
              {previewRows.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-slate-700">Preview (first {previewRows.length} transformed rows)</p>
                  <div className="overflow-x-auto rounded-lg border border-slate-200 text-xs max-h-48">
                    <table className="w-full">
                      <thead className="bg-slate-50 sticky top-0">
                        <tr>
                          {Object.keys(previewRows[0]).filter(k => !k.startsWith('_raw_')).slice(0, 8).map(h => (
                            <th key={h} className="px-3 py-2 text-left text-slate-500 font-semibold whitespace-nowrap">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {previewRows.map((row, i) => (
                          <tr key={i}>
                            {Object.entries(row).filter(([k]) => !k.startsWith('_raw_')).slice(0, 8).map(([k, v]) => (
                              <td key={k} className="px-3 py-1.5 text-slate-700 whitespace-nowrap max-w-24 truncate">{String(v ?? '')}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3">
                <button onClick={handlePreview} disabled={step === 'previewing'}
                  className="flex items-center gap-2 px-5 py-2.5 border border-slate-200 rounded-xl text-slate-600 hover:bg-slate-50 text-sm font-medium transition-colors disabled:opacity-50">
                  {step === 'previewing' ? <Spinner size="sm" /> : <Eye size={15} />}
                  Preview Transformation
                </button>
                <button onClick={handleRun}
                  className="flex-1 bg-accent-blue hover:bg-accent-blue-light text-white font-semibold py-2.5 rounded-xl transition-colors flex items-center justify-center gap-2">
                  <Play size={15} /> Confirm & Run ETL
                </button>
              </div>
            </motion.div>
          )}

          {/* ── RUNNING ── */}
          {step === 'running' && etlJobId && (
            <motion.div key="running" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <h3 className="font-semibold text-slate-800 mb-5">ETL Pipeline Running</h3>
              <ETLProgress jobId={etlJobId} onReset={reset} />
            </motion.div>
          )}

          {/* ── ERROR ── */}
          {step === 'error' && (
            <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="py-10 text-center space-y-3">
              <XCircle size={48} className="mx-auto text-red-400" />
              <p className="font-semibold text-red-700">{error || 'Something went wrong.'}</p>
              <button onClick={reset} className="text-accent-blue underline text-sm">Try again</button>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>

      {/* ── Upload history ── */}
      <Card padding="none">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <SectionHeader title="Upload History" />
          <button onClick={() => refetchHistory()}
            className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
            <RefreshCw size={15} />
          </button>
        </div>
        <Table columns={HISTORY_COLS as any} data={history as any[]}
          emptyMessage="No uploads yet." />
      </Card>
    </div>
  )
}
