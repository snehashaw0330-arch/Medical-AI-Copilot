import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Workflow,
  Sparkles,
  RotateCcw,
  History as HistoryIcon,
  ChevronRight,
  BrainCog,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import TagInput from '@/ui/TagInput'
import EmptyState from '@/ui/EmptyState'
import ReasoningPipeline from '@/ui/ReasoningPipeline'
import ClinicalReasoningReport from '@/ui/ClinicalReasoningReport'
import {
  analyzeReasoning,
  getReasoningPipeline,
  getReasoningHistory,
  getReasoningReport,
  getSymptoms,
} from '@/lib/api'
import { errorMessage, titleCase, formatDate } from '@/lib/utils'

const RISK_TONE = { critical: 'danger', high: 'danger', moderate: 'warning', low: 'primary' }

// Fallback pipeline shown before the backend definition loads.
const FALLBACK_STEPS = [
  { order: 1, key: 'ocr', name: 'OCR' },
  { order: 2, key: 'medicine_detection', name: 'Medicine Detection' },
  { order: 3, key: 'medicine_validation', name: 'Medicine Validation' },
  { order: 4, key: 'drug_interactions', name: 'Drug Interaction Analysis' },
  { order: 5, key: 'disease_prediction', name: 'Disease Prediction' },
  { order: 6, key: 'evidence_retrieval', name: 'Retrieve Medical Evidence (RAG)' },
  { order: 7, key: 'clinical_rules', name: 'Clinical Rules Evaluation' },
  { order: 8, key: 'differential', name: 'Differential Diagnosis' },
  { order: 9, key: 'confidence', name: 'Confidence Calculation' },
  { order: 10, key: 'recommendation', name: 'Final Recommendation' },
]

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}

function HistoryRow({ item, onOpen }) {
  const tone = RISK_TONE[item.risk_level] || 'primary'
  return (
    <button
      onClick={() => onOpen(item.id)}
      className="flex w-full items-center gap-3 rounded-xl border border-border bg-surface p-3 text-left transition-colors hover:bg-surface-2"
    >
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-2 text-primary">
        <BrainCog size={16} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">
          {item.leading_disease ? titleCase(item.leading_disease) : `${item.medicine_count} medicine(s)`}
        </p>
        <p className="truncate text-xs text-muted">
          {formatDate(item.created_at)} · {item.confidence?.toFixed(0)}% conf
        </p>
      </div>
      <Badge tone={tone}>{titleCase(item.risk_level)}</Badge>
      <ChevronRight size={16} className="shrink-0 text-muted" />
    </button>
  )
}

// Live animated pipeline shown while the reasoning runs on the server.
function RunningPipeline({ steps }) {
  const [activeIdx, setActiveIdx] = useState(0)
  useEffect(() => {
    const id = setInterval(() => {
      setActiveIdx((i) => (i + 1) % steps.length)
    }, 700)
    return () => clearInterval(id)
  }, [steps.length])

  // Mark everything before the active node complete, the active one running.
  const decorated = steps.map((s, i) => ({
    ...s,
    status: i < activeIdx ? 'complete' : i === activeIdx ? 'running' : 'pending',
    title: i === activeIdx ? 'Reasoning…' : '',
  }))
  return (
    <Card className="animate-fade-up">
      <CardHeader
        icon={Workflow}
        title="Reasoning in progress"
        subtitle="The platform is thinking step by step"
      />
      <ReasoningPipeline steps={decorated} compact />
    </Card>
  )
}

export default function ClinicalReasoning() {
  const [medicines, setMedicines] = useState([])
  const [symptoms, setSymptoms] = useState([])
  const [symptomOptions, setSymptomOptions] = useState([])
  const [diagnosis, setDiagnosis] = useState('')
  const [age, setAge] = useState('')
  const [gender, setGender] = useState('')
  const [includeRag, setIncludeRag] = useState(true)
  const [loading, setLoading] = useState(false)
  const [report, setReport] = useState(null)
  const [pipelineDef, setPipelineDef] = useState(FALLBACK_STEPS)
  const [history, setHistory] = useState([])
  const reportRef = useRef(null)

  const refreshHistory = () =>
    getReasoningHistory({ page_size: 6 })
      .then((d) => setHistory(d.items || []))
      .catch(() => setHistory([]))

  useEffect(() => {
    getSymptoms().then(setSymptomOptions).catch(() => setSymptomOptions([]))
    getReasoningPipeline().then((s) => s.length && setPipelineDef(s)).catch(() => {})
    refreshHistory()
  }, [])

  const run = async () => {
    if (!medicines.length && !symptoms.length && !diagnosis.trim()) {
      toast.error('Add at least one medicine, symptom, or a diagnosis.')
      return
    }
    setLoading(true)
    setReport(null)
    try {
      const data = await analyzeReasoning({
        medicines,
        symptoms,
        diagnosis: diagnosis.trim() || null,
        age: age ? Number(age) : null,
        gender: gender || null,
        include_rag: includeRag,
        run_disease_prediction: true,
        use_cache: true,
      })
      setReport(data)
      refreshHistory()
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
    } catch (err) {
      toast.error(errorMessage(err, 'Clinical reasoning failed. Is the backend running?'))
    } finally {
      setLoading(false)
    }
  }

  const openHistory = async (id) => {
    setLoading(true)
    try {
      setReport(await getReasoningReport(id))
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load that report.'))
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setMedicines([]); setSymptoms([]); setDiagnosis(''); setAge(''); setGender('')
    setReport(null)
  }

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      {/* ---- Input panel ---- */}
      <div className="lg:col-span-2">
        <Card className="lg:sticky lg:top-24">
          <CardHeader
            icon={Workflow}
            title="AI Clinical Reasoning"
            subtitle="Step-by-step reasoning across OCR, medicines, disease, evidence & rules"
          />

          <div className="space-y-4">
            <Field label="Medicines">
              <TagInput value={medicines} onChange={setMedicines} placeholder="e.g. Warfarin, Aspirin…" />
            </Field>

            <Field label="Symptoms">
              <TagInput
                value={symptoms}
                onChange={setSymptoms}
                suggestions={symptomOptions}
                placeholder="e.g. chest pain, shortness of breath…"
              />
            </Field>

            <Field label="Known / suspected diagnosis (optional)">
              <input
                value={diagnosis}
                onChange={(e) => setDiagnosis(e.target.value)}
                placeholder="e.g. Hypertension"
                className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary"
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Age">
                <input
                  type="number" min="0" max="120"
                  value={age}
                  onChange={(e) => setAge(e.target.value)}
                  placeholder="Years"
                  className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary"
                />
              </Field>
              <Field label="Gender">
                <select
                  value={gender}
                  onChange={(e) => setGender(e.target.value)}
                  className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary"
                >
                  <option value="">Unspecified</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </select>
              </Field>
            </div>

            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={includeRag}
                onChange={(e) => setIncludeRag(e.target.checked)}
                className="h-4 w-4 rounded border-border accent-[var(--primary)]"
              />
              Retrieve knowledge-base evidence (RAG)
            </label>

            <div className="flex gap-2 pt-1">
              <Button className="flex-1" onClick={run} loading={loading}>
                <Sparkles size={16} /> Run Reasoning
              </Button>
              <Button variant="secondary" onClick={reset} aria-label="Reset form">
                <RotateCcw size={16} />
              </Button>
            </div>
            <p className="text-xs text-muted">
              Educational decision support only — every step and recommendation must be
              confirmed by a qualified clinician.
            </p>
          </div>

          {history.length > 0 && (
            <div className="mt-6 border-t border-border pt-4">
              <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <HistoryIcon size={15} className="text-primary" /> Recent reasoning
              </p>
              <div className="space-y-2">
                {history.map((h) => (
                  <HistoryRow key={h.id} item={h} onOpen={openHistory} />
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* ---- Report panel ---- */}
      <div ref={reportRef} className="space-y-5 lg:col-span-3">
        {loading && !report ? (
          <RunningPipeline steps={pipelineDef} />
        ) : report ? (
          <ClinicalReasoningReport report={report} />
        ) : (
          <EmptyState
            icon={BrainCog}
            title="Your clinical reasoning report will appear here"
            description="Enter the patient's medicines, symptoms and details, then run reasoning. The platform walks a transparent pipeline — OCR, medicine validation, drug interactions, disease prediction, evidence retrieval, clinical rules, differential, confidence and recommendation — and shows every step of its work."
          />
        )}
      </div>
    </div>
  )
}
