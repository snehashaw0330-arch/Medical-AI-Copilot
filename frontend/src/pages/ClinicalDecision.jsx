import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  BrainCircuit,
  Pill,
  Stethoscope,
  Sparkles,
  RotateCcw,
  History as HistoryIcon,
  ChevronRight,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import TagInput from '@/ui/TagInput'
import EmptyState from '@/ui/EmptyState'
import ClinicalReport from '@/ui/ClinicalReport'
import {
  analyzeClinical,
  getSymptoms,
  getClinicalHistory,
  getClinicalReport,
} from '@/lib/api'
import { errorMessage, titleCase, formatDate } from '@/lib/utils'

// Risk level → badge tone (mirrors ui/ClinicalReport + backend RiskLevel).
const RISK_TONE = { critical: 'danger', high: 'danger', moderate: 'warning', low: 'primary' }

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
        <Stethoscope size={16} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">
          {item.top_disease ? titleCase(item.top_disease) : `${item.medicine_count} medicine(s)`}
        </p>
        <p className="truncate text-xs text-muted">{formatDate(item.created_at)}</p>
      </div>
      <Badge tone={tone}>{titleCase(item.risk_level)}</Badge>
      <ChevronRight size={16} className="shrink-0 text-muted" />
    </button>
  )
}

export default function ClinicalDecision() {
  const [medicines, setMedicines] = useState([])
  const [symptoms, setSymptoms] = useState([])
  const [symptomOptions, setSymptomOptions] = useState([])
  const [diagnosis, setDiagnosis] = useState('')
  const [age, setAge] = useState('')
  const [gender, setGender] = useState('')
  const [loading, setLoading] = useState(false)
  const [report, setReport] = useState(null)
  const [history, setHistory] = useState([])
  const reportRef = useRef(null)

  // Symptom autocomplete reuses the disease-prediction symptom vocabulary.
  useEffect(() => {
    getSymptoms().then(setSymptomOptions).catch(() => setSymptomOptions([]))
    refreshHistory()
  }, [])

  const refreshHistory = () =>
    getClinicalHistory({ page_size: 6 })
      .then((d) => setHistory(d.items || []))
      .catch(() => setHistory([]))

  const run = async () => {
    if (!medicines.length && !symptoms.length && !diagnosis.trim()) {
      toast.error('Add at least one medicine, symptom, or a diagnosis.')
      return
    }
    setLoading(true)
    setReport(null)
    try {
      const data = await analyzeClinical({
        medicines,
        symptoms,
        diagnosis: diagnosis.trim() || null,
        age: age ? Number(age) : null,
        gender: gender || null,
        include_rag: true,
        run_disease_prediction: true,
        persist: true,
      })
      setReport(data)
      refreshHistory()
      // Bring the report into view on small screens.
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
    } catch (err) {
      toast.error(errorMessage(err, 'Clinical analysis failed. Is the backend running?'))
    } finally {
      setLoading(false)
    }
  }

  const openHistory = async (id) => {
    setLoading(true)
    try {
      setReport(await getClinicalReport(id))
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
            icon={BrainCircuit}
            title="Clinical Decision Support"
            subtitle="Synthesise symptoms, medicines, disease & interactions into one report"
          />

          <div className="space-y-4">
            <Field label="Medicines">
              <TagInput
                value={medicines}
                onChange={setMedicines}
                placeholder="e.g. Warfarin, Ibuprofen…"
              />
            </Field>

            <Field label="Symptoms">
              <TagInput
                value={symptoms}
                onChange={setSymptoms}
                suggestions={symptomOptions}
                placeholder="e.g. chest pain, fever…"
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

            <div className="flex gap-2 pt-1">
              <Button className="flex-1" onClick={run} loading={loading}>
                <Sparkles size={16} /> Analyze
              </Button>
              <Button variant="secondary" onClick={reset} aria-label="Reset form">
                <RotateCcw size={16} />
              </Button>
            </div>
            <p className="text-xs text-muted">
              Educational decision support only — every finding must be confirmed by a
              qualified clinician.
            </p>
          </div>

          {/* Recent analyses */}
          {history.length > 0 && (
            <div className="mt-6 border-t border-border pt-4">
              <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <HistoryIcon size={15} className="text-primary" /> Recent reports
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
        {report ? (
          <ClinicalReport report={report} />
        ) : (
          <EmptyState
            icon={Pill}
            title="Your clinical report will appear here"
            description="Enter the patient's medicines, symptoms and details, then tap Analyze. The system runs disease prediction, drug-interaction analysis and the clinical rules engine, then grades the overall risk."
          />
        )}
      </div>
    </div>
  )
}
