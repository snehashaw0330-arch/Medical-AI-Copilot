import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Database,
  Play,
  Loader2,
  FileDown,
  CheckCircle2,
  AlertTriangle,
  Image as ImageIcon,
  Pill,
  Gauge,
  Timer,
  Target,
  XCircle,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import ConfidenceBar from '@/ui/ConfidenceBar'
import {
  getDatasetInfo,
  startDatasetEvaluation,
  getDatasetEvaluationStatus,
  datasetReportUrl,
} from '@/lib/api'
import { errorMessage, titleCase, confidenceColor } from '@/lib/utils'

const POLL_MS = 2000
const pct = (v) => Math.round((v || 0) * 100)

// ---------- small presentational pieces ----------
function MetricCard({ icon: Icon, label, value }) {
  return (
    <Card className="flex items-center gap-3">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary-soft text-primary">
        <Icon size={20} />
      </span>
      <div className="min-w-0">
        <p className="text-xs text-muted">{label}</p>
        <p className="text-xl font-bold text-foreground">{value}</p>
      </div>
    </Card>
  )
}

function ResultRow({ r }) {
  const failed = r.status === 'failed'
  const conf = pct(r.overall_confidence)
  return (
    <div className="flex items-start gap-3 border-b border-border py-3 last:border-0">
      <span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg ${
        failed ? 'bg-danger/15 text-danger' : 'bg-success/15 text-success'
      }`}>
        {failed ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 truncate text-sm font-medium text-foreground">
            <ImageIcon size={14} className="text-muted" /> {r.image}
          </p>
          {failed ? (
            <Badge tone="danger">Failed</Badge>
          ) : (
            <span className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold"
                  style={{ color: confidenceColor(conf), backgroundColor: `${confidenceColor(conf)}1a` }}>
              {conf}%
            </span>
          )}
        </div>
        {failed ? (
          <p className="mt-1 text-xs text-danger/80">{r.error || 'Processing error'}</p>
        ) : (
          <>
            <p className="mt-1 text-xs text-muted">
              {r.best_engine ? <>Engine <span className="font-medium text-foreground">{r.best_engine}</span> · </> : null}
              {r.medicine_count} medicine{r.medicine_count === 1 ? '' : 's'} · {r.processing_time}s
            </p>
            {r.medicines?.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {r.medicines.slice(0, 8).map((m, i) => (
                  <Badge key={i} tone="primary">{titleCase(m)}</Badge>
                ))}
                {r.medicines.length > 8 && (
                  <Badge tone="neutral">+{r.medicines.length - 8} more</Badge>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ---------- page ----------
export default function DatasetEvaluation() {
  const [info, setInfo] = useState(null)        // { image_count, dataset, exists }
  const [job, setJob] = useState(null)          // latest status payload
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')   // all | failed
  const pollRef = useRef(null)

  // Load dataset size on mount so the user sees what they're about to run.
  useEffect(() => {
    getDatasetInfo().then(setInfo).catch(() => setInfo(null))
    return () => clearInterval(pollRef.current)
  }, [])

  const poll = (jobId) => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const status = await getDatasetEvaluationStatus(jobId)
        setJob(status)
        if (status.status !== 'running') {
          clearInterval(pollRef.current)
          setRunning(false)
          if (status.status === 'completed') toast.success('Evaluation complete')
          if (status.status === 'failed') setError(status.error || 'Evaluation failed')
        }
      } catch (err) {
        clearInterval(pollRef.current)
        setRunning(false)
        setError(errorMessage(err, 'Lost connection to the evaluation job.'))
      }
    }, POLL_MS)
  }

  const run = async () => {
    setError(null)
    setRunning(true)
    setJob(null)
    try {
      const started = await startDatasetEvaluation()
      setJob(started)
      poll(started.job_id)
    } catch (err) {
      setRunning(false)
      setError(errorMessage(err, 'Could not start the evaluation.'))
    }
  }

  const total = job?.total ?? info?.image_count ?? 0
  const done = (job?.processed ?? 0) + (job?.failed ?? 0)
  const progress = total ? Math.round((done / total) * 100) : 0
  const metrics = job?.report?.metrics
  const results = job?.report?.results ?? []
  const completed = job?.status === 'completed'

  const shown = filter === 'failed' ? results.filter((r) => r.status === 'failed') : results

  return (
    <div className="space-y-6">
      {/* Header / control panel */}
      <Card>
        <CardHeader
          icon={Database}
          title="Dataset Evaluation"
          subtitle="Batch-run the handwritten prescription dataset through the OCR pipeline"
          action={
            <Button onClick={run} loading={running} disabled={running || !info?.image_count}>
              {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {running ? 'Evaluating…' : 'Run Evaluation'}
            </Button>
          }
        />
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
          <Badge tone="neutral"><ImageIcon size={12} /> {info?.image_count ?? '—'} images</Badge>
          {info?.dataset && (
            <span className="truncate font-mono text-xs text-muted">{info.dataset}</span>
          )}
        </div>

        {/* Progress */}
        {(running || job) && (
          <div className="mt-5">
            <div className="mb-1 flex justify-between text-xs font-medium text-muted">
              <span>
                {job?.status === 'running' && job?.current_image
                  ? `Processing ${job.current_image}…`
                  : completed
                  ? 'Completed'
                  : job?.status === 'failed'
                  ? 'Failed'
                  : 'Starting…'}
              </span>
              <span>{done}/{total} ({progress}%)</span>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4 flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-foreground">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-danger" />
            <span>{error}</span>
          </div>
        )}
      </Card>

      {/* Metrics */}
      {metrics && (
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCard icon={ImageIcon} label="Total images" value={metrics.total_images} />
          <MetricCard icon={CheckCircle2} label="Processed" value={metrics.processed_images} />
          <MetricCard icon={XCircle} label="Failed" value={metrics.failed_images} />
          <MetricCard icon={Gauge} label="Avg. OCR confidence" value={`${pct(metrics.average_confidence)}%`} />
          <MetricCard icon={Target} label="Medicine extraction" value={`${pct(metrics.medicine_extraction_accuracy)}%`} />
          <MetricCard icon={Timer} label="Avg. time / image" value={`${metrics.average_processing_time}s`} />
        </section>
      )}

      {/* Summary + download */}
      {completed && metrics && (
        <Card className="border-success/30 bg-success/5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-success/15 text-success">
                <CheckCircle2 size={26} />
              </span>
              <div>
                <h2 className="text-lg font-bold text-foreground">Evaluation Complete</h2>
                <p className="text-sm text-muted">
                  {metrics.processed_images} processed · {metrics.failed_images} failed ·{' '}
                  {metrics.total_medicines_extracted} medicines extracted
                </p>
              </div>
            </div>
            <a href={datasetReportUrl(job.job_id)} target="_blank" rel="noreferrer" download>
              <Button variant="secondary"><FileDown size={15} /> Download Report (JSON)</Button>
            </a>
          </div>
        </Card>
      )}

      {/* Per-image results */}
      {results.length > 0 ? (
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <CardHeader icon={Pill} title="Per-image results" subtitle={`${results.length} of ${total} images`} />
            <div className="flex gap-1.5">
              <Button size="sm" variant={filter === 'all' ? 'primary' : 'secondary'} onClick={() => setFilter('all')}>All</Button>
              <Button size="sm" variant={filter === 'failed' ? 'primary' : 'secondary'} onClick={() => setFilter('failed')}>
                Failed ({results.filter((r) => r.status === 'failed').length})
              </Button>
            </div>
          </div>
          <div className="max-h-[32rem] overflow-auto pr-1">
            {shown.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted">No images in this view.</p>
            ) : (
              shown.map((r, i) => <ResultRow key={i} r={r} />)
            )}
          </div>
        </Card>
      ) : (
        !running && !job && (
          <EmptyState
            icon={Database}
            title="No evaluation run yet"
            description="Click Run Evaluation to process the full handwritten prescription dataset through the OCR pipeline. Local handwriting OCR is slow, so this can take several minutes — progress updates live."
          />
        )
      )}

      {/* Live progress placeholder while running and report not yet built */}
      {running && results.length === 0 && (
        <Card className="flex flex-col items-center justify-center gap-3 py-14 text-center">
          <Loader2 size={28} className="animate-spin text-primary" />
          <p className="font-medium text-foreground">Evaluating the dataset…</p>
          <p className="text-sm text-muted">
            Each image is preprocessed and read by the OCR ensemble. Results appear here as the job finishes.
          </p>
          {total > 0 && <div className="w-full max-w-md"><ConfidenceBar value={progress} showLabel={false} /></div>}
        </Card>
      )}
    </div>
  )
}
