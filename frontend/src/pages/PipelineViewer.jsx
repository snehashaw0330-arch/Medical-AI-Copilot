import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  Layers, ChevronRight, CheckCircle2, AlertTriangle, MinusCircle, XCircle,
  Upload, ScanLine, Pill, Stethoscope, ShieldAlert, BookOpen, BrainCircuit,
  FileText, Clock,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import { CardSkeleton } from '@/ui/Skeleton'
import { searchDecisions, getDecisionPipeline } from '@/lib/api'
import { errorMessage, formatDate, confidenceColor } from '@/lib/utils'

const STEP_ICON = {
  upload: Upload, ocr: ScanLine, medicine_matching: Pill, disease_prediction: Stethoscope,
  drug_interaction: ShieldAlert, rag_retrieval: BookOpen, clinical_decision: BrainCircuit,
  report_generation: FileText,
}
const STEP_STATUS = {
  completed: { tone: 'success', icon: CheckCircle2, color: 'var(--success)' },
  warning: { tone: 'warning', icon: AlertTriangle, color: 'var(--warning)' },
  skipped: { tone: 'neutral', icon: MinusCircle, color: 'var(--muted)' },
  failed: { tone: 'danger', icon: XCircle, color: 'var(--danger)' },
}
const st = (s) => STEP_STATUS[s] || STEP_STATUS.completed

function StepCard({ step }) {
  const cfg = st(step.status)
  const Icon = STEP_ICON[step.key] || Layers
  const StatusIcon = cfg.icon
  const skipped = step.status === 'skipped'
  return (
    <div className={`relative rounded-2xl border bg-surface p-4 shadow-sm ${skipped ? 'opacity-60' : ''}`}
      style={{ borderColor: skipped ? 'var(--border)' : cfg.color }}>
      <div className="flex items-start justify-between gap-2">
        <span className="grid h-10 w-10 place-items-center rounded-xl" style={{ background: 'var(--surface-2)' }}>
          <Icon size={19} style={{ color: cfg.color }} />
        </span>
        <StatusIcon size={16} style={{ color: cfg.color }} />
      </div>
      <p className="mt-2 text-sm font-semibold text-foreground">{step.name}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className="inline-flex items-center gap-1"><Clock size={11} /> {(step.execution_time || 0).toFixed(3)}s</span>
        {step.confidence != null && (
          <span className="font-semibold" style={{ color: confidenceColor(step.confidence * 100) }}>
            {Math.round(step.confidence * 100)}%
          </span>
        )}
      </div>
      {step.detail && <p className="mt-1.5 text-xs text-muted">{step.detail}</p>}
      {step.warnings?.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {step.warnings.map((w, i) => (
            <li key={i} className="flex gap-1.5 text-[11px] text-warning"><AlertTriangle size={11} className="mt-0.5 shrink-0" />{w}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function PipelineViewer() {
  const [params, setParams] = useSearchParams()
  const traceParam = params.get('trace') || ''
  const [decisions, setDecisions] = useState([])
  const [traceId, setTraceId] = useState(traceParam)
  const [pipeline, setPipeline] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async (id) => {
    if (!id) return
    setTraceId(id)
    setParams({ trace: id }, { replace: true })
    setLoading(true)
    try {
      setPipeline(await getDecisionPipeline(id))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load the pipeline'))
    } finally { setLoading(false) }
  }

  useEffect(() => {
    searchDecisions({ page_size: 50 })
      .then((page) => {
        const items = page.items || []
        setDecisions(items)
        const initial = traceParam || (items[0] && items[0].trace_id)
        if (initial) load(initial)
      })
      .catch((err) => toast.error(errorMessage(err, 'Could not load decisions')))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-foreground">
            <Layers size={22} className="text-primary" /> Pipeline Viewer
          </h1>
          <p className="text-sm text-muted">The end-to-end AI workflow for one decision — time, status, confidence & warnings per step.</p>
        </div>
        <select value={traceId} onChange={(e) => load(e.target.value)} disabled={!decisions.length}
          className="h-10 max-w-xs rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary">
          {!decisions.length && <option>No decisions yet</option>}
          {decisions.map((d) => (
            <option key={d.trace_id} value={d.trace_id}>
              {(d.patient_name || 'Unknown')} · {d.top_disease || 'n/a'} · {formatDate(d.created_at)?.split(',')[0]}
            </option>
          ))}
        </select>
      </div>

      {!decisions.length && !loading && (
        <EmptyState icon={Layers} title="No decisions to visualise"
          description="Analyse a prescription or sync the governance store to populate decision traces." />
      )}

      {loading && <CardSkeleton />}

      {!loading && pipeline && (
        <>
          <Card className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm">
              <Badge tone={st(pipeline.status === 'success' ? 'completed' : pipeline.status).tone}>{pipeline.status}</Badge>
              <span className="text-muted">Total execution</span>
              <span className="font-bold text-foreground">{(pipeline.total_time || 0).toFixed(3)}s</span>
            </div>
            <p className="font-mono text-xs text-muted">{pipeline.trace_id}</p>
          </Card>

          {/* the visual workflow — cards with connectors */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {pipeline.steps.map((step, i) => (
              <div key={step.key} className="relative">
                <StepCard step={step} />
                {i < pipeline.steps.length - 1 && (
                  <ChevronRight size={18} className="absolute -right-3 top-1/2 hidden -translate-y-1/2 text-border lg:block" />
                )}
              </div>
            ))}
          </div>

          {/* linear legend of the canonical flow */}
          <Card>
            <CardHeader icon={Layers} title="Canonical AI Pipeline" />
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
              {['Image Upload', 'OCR', 'Medicine Matching', 'Disease Prediction', 'Drug Interaction', 'RAG Retrieval', 'Clinical Decision', 'Report Generation'].map((n, i, arr) => (
                <span key={n} className="inline-flex items-center gap-2">
                  <span className="font-medium text-foreground">{n}</span>
                  {i < arr.length - 1 && <ChevronRight size={13} />}
                </span>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
