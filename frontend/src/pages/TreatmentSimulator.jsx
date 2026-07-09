import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  FlaskConical,
  Pill,
  User,
  Plus,
  Trash2,
  Sparkles,
  RotateCcw,
  GitCompareArrows,
  ShieldAlert,
  BookOpen,
  ClipboardCheck,
  TriangleAlert,
  Beaker,
  Trophy,
  ArrowRight,
  History as HistoryIcon,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import TagInput from '@/ui/TagInput'
import EmptyState from '@/ui/EmptyState'
import ConfidenceMeter from '@/ui/ConfidenceMeter'
import { runSimulation, getSimulationHistory, getSimulationReport, getSymptoms } from '@/lib/api'
import { errorMessage, titleCase, formatDate } from '@/lib/utils'

const RISK_TONE = { critical: 'danger', high: 'danger', moderate: 'warning', low: 'success' }
const RISK_COLOR = { critical: 'var(--danger)', high: 'var(--danger)', moderate: 'var(--warning)', low: 'var(--success)' }
const ORGAN_OPTS = ['none', 'mild', 'moderate', 'severe']
const ACTIONS = [
  ['dosage_change', 'Change dose'],
  ['replace', 'Replace'],
  ['remove', 'Remove'],
  ['add', 'Add'],
]

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:border-primary'

let scenarioCounter = 0
const nextScenarioName = () => `Scenario ${String.fromCharCode(65 + scenarioCounter++ % 26)}`

// ---------- Editable baseline medicines ----------
function MedicineEditor({ value, onChange }) {
  const update = (i, patch) => onChange(value.map((m, idx) => (idx === i ? { ...m, ...patch } : m)))
  const remove = (i) => onChange(value.filter((_, idx) => idx !== i))
  const add = () => onChange([...value, { name: '', dose: '', unit: 'mg' }])
  return (
    <div className="space-y-2">
      {value.map((m, i) => (
        <div key={i} className="flex items-center gap-2">
          <input className={inputCls} placeholder="Medicine" value={m.name}
            onChange={(e) => update(i, { name: e.target.value })} />
          <input className={`${inputCls} w-20`} placeholder="Dose" value={m.dose ?? ''}
            onChange={(e) => update(i, { dose: e.target.value })} />
          <select className={`${inputCls} w-20`} value={m.unit}
            onChange={(e) => update(i, { unit: e.target.value })}>
            {['mg', 'mcg', 'g', 'ml', 'units'].map((u) => <option key={u}>{u}</option>)}
          </select>
          <button onClick={() => remove(i)} className="shrink-0 text-muted hover:text-danger" aria-label="Remove">
            <Trash2 size={16} />
          </button>
        </div>
      ))}
      <Button size="sm" variant="secondary" onClick={add}><Plus size={14} /> Add medicine</Button>
    </div>
  )
}

// ---------- Scenario editor ----------
function ScenarioEditor({ scenario, baselineNames, onChange, onRemove }) {
  const setChange = (i, patch) =>
    onChange({ ...scenario, medicine_changes: scenario.medicine_changes.map((c, idx) => (idx === i ? { ...c, ...patch } : c)) })
  const addChange = () =>
    onChange({ ...scenario, medicine_changes: [...scenario.medicine_changes, { action: 'dosage_change', target: baselineNames[0] || '', name: '', dose: '', unit: 'mg' }] })
  const removeChange = (i) =>
    onChange({ ...scenario, medicine_changes: scenario.medicine_changes.filter((_, idx) => idx !== i) })
  const setPatient = (patch) => onChange({ ...scenario, patient_changes: { ...scenario.patient_changes, ...patch } })
  const pc = scenario.patient_changes || {}

  return (
    <div className="rounded-xl border border-border bg-surface-2/40 p-3">
      <div className="mb-2 flex items-center gap-2">
        <Beaker size={15} className="text-primary" />
        <input className={`${inputCls} max-w-[12rem] font-medium`} value={scenario.name}
          onChange={(e) => onChange({ ...scenario, name: e.target.value })} />
        <button onClick={onRemove} className="ml-auto text-muted hover:text-danger" aria-label="Remove scenario">
          <Trash2 size={16} />
        </button>
      </div>

      {/* Medicine changes */}
      <div className="space-y-2">
        {scenario.medicine_changes.map((c, i) => (
          <div key={i} className="flex flex-wrap items-center gap-1.5">
            <select className={`${inputCls} w-32`} value={c.action} onChange={(e) => setChange(i, { action: e.target.value })}>
              {ACTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            {c.action !== 'add' && (
              <select className={`${inputCls} w-32`} value={c.target} onChange={(e) => setChange(i, { target: e.target.value })}>
                <option value="">target…</option>
                {baselineNames.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            )}
            {(c.action === 'add' || c.action === 'replace') && (
              <input className={`${inputCls} w-28`} placeholder="new name" value={c.name}
                onChange={(e) => setChange(i, { name: e.target.value })} />
            )}
            {c.action !== 'remove' && (
              <input className={`${inputCls} w-16`} placeholder="dose" value={c.dose ?? ''}
                onChange={(e) => setChange(i, { dose: e.target.value })} />
            )}
            <button onClick={() => removeChange(i)} className="text-muted hover:text-danger" aria-label="Remove change">
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <Button size="sm" variant="ghost" onClick={addChange}><Plus size={14} /> Add change</Button>
      </div>

      {/* Patient overrides */}
      <div className="mt-3 border-t border-border pt-2">
        <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">Patient overrides (optional)</p>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={!!pc.pregnant} onChange={(e) => setPatient({ pregnant: e.target.checked })} />
            Pregnant
          </label>
          <label className="flex items-center gap-1">Renal
            <select className={`${inputCls} h-8 w-24`} value={pc.renal_disease || 'none'} onChange={(e) => setPatient({ renal_disease: e.target.value })}>
              {ORGAN_OPTS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">Hepatic
            <select className={`${inputCls} h-8 w-24`} value={pc.hepatic_disease || 'none'} onChange={(e) => setPatient({ hepatic_disease: e.target.value })}>
              {ORGAN_OPTS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">Age
            <input className={`${inputCls} h-8 w-16`} value={pc.age ?? ''} onChange={(e) => setPatient({ age: e.target.value })} />
          </label>
          <label className="flex items-center gap-1">Wt(kg)
            <input className={`${inputCls} h-8 w-16`} value={pc.weight_kg ?? ''} onChange={(e) => setPatient({ weight_kg: e.target.value })} />
          </label>
        </div>
      </div>
    </div>
  )
}

// ---------- Risk meter ----------
function RiskMeter({ level, score }) {
  const pct = Math.max(0, Math.min(100, score || 0))
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-medium text-muted">Composite risk</span>
        <span className="font-semibold" style={{ color: RISK_COLOR[level] }}>{Math.round(pct)} / 100 · {titleCase(level)}</span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div className="meter-fill h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: RISK_COLOR[level] }} />
      </div>
    </div>
  )
}

// ---------- One scenario result ----------
function ScenarioResultCard({ result, recommended }) {
  const interactions = result.drug_interactions?.interactions || []
  return (
    <Card className={`animate-fade-up ${recommended ? 'border-success/50' : ''}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`grid h-9 w-9 place-items-center rounded-xl ${result.is_baseline ? 'bg-surface-2 text-muted' : 'bg-primary-soft text-primary'}`}>
            {result.is_baseline ? <Pill size={18} /> : <Beaker size={18} />}
          </span>
          <div>
            <h3 className="font-semibold text-foreground">{result.scenario_name}</h3>
            <p className="text-xs text-muted">{result.resulting_medicines.map((m) => m.name).join(', ') || 'No medicines'}</p>
          </div>
        </div>
        {recommended && <Badge tone="success"><Trophy size={13} /> Recommended</Badge>}
      </div>

      <RiskMeter level={result.risk_level} score={result.risk_score} />

      {result.applied_changes?.length > 0 && !result.is_baseline && (
        <ul className="mt-3 space-y-1 text-xs text-muted">
          {result.applied_changes.map((c, i) => <li key={i}>• {c}</li>)}
        </ul>
      )}

      {result.contraindications?.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 flex items-center gap-1 text-xs font-semibold text-danger"><ShieldAlert size={13} /> Contraindications</p>
          <div className="space-y-1">
            {result.contraindications.map((c, i) => (
              <div key={i} className="rounded-lg bg-danger/10 px-2 py-1 text-xs text-danger">
                <span className="font-medium">{titleCase(c.medicine)}</span> — {c.reason}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
        <Stat label="Interactions" value={interactions.length} tone={interactions.length ? 'warning' : 'success'} />
        <Stat label="Side effects" value={result.side_effects.length} />
        <Stat label="Confidence" value={`${Math.round(result.confidence.overall)}%`} />
      </div>
    </Card>
  )
}

function Stat({ label, value, tone }) {
  const color = tone === 'warning' ? 'text-warning' : tone === 'success' ? 'text-success' : 'text-foreground'
  return (
    <div className="rounded-lg bg-surface-2/60 p-2">
      <div className={`text-lg font-bold ${color}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
    </div>
  )
}

export default function TreatmentSimulator() {
  const [baselineMeds, setBaselineMeds] = useState([
    { name: 'Paracetamol', dose: 500, unit: 'mg' },
    { name: 'Amoxicillin', dose: 500, unit: 'mg' },
  ])
  const [patient, setPatient] = useState({ age: '', weight_kg: '', gender: '', pregnant: false, renal_disease: 'none', hepatic_disease: 'none' })
  const [allergies, setAllergies] = useState([])
  const [symptoms, setSymptoms] = useState([])
  const [symptomOptions, setSymptomOptions] = useState([])
  const [scenarios, setScenarios] = useState([
    { name: nextScenarioName(), medicine_changes: [{ action: 'dosage_change', target: 'Paracetamol', name: '', dose: 650, unit: 'mg' }], patient_changes: {} },
  ])
  const [includeRag, setIncludeRag] = useState(false)
  const [loading, setLoading] = useState(false)
  const [report, setReport] = useState(null)
  const [history, setHistory] = useState([])
  const resultRef = useRef(null)

  const refreshHistory = () =>
    getSimulationHistory({ page_size: 6 }).then((d) => setHistory(d.items || [])).catch(() => setHistory([]))

  useEffect(() => {
    getSymptoms().then(setSymptomOptions).catch(() => setSymptomOptions([]))
    refreshHistory()
  }, [])

  const baselineNames = baselineMeds.map((m) => m.name).filter(Boolean)

  const addScenario = () =>
    setScenarios((s) => [...s, { name: nextScenarioName(), medicine_changes: [], patient_changes: {} }])

  const cleanNum = (v) => (v === '' || v === null || v === undefined ? null : Number(v))

  const buildPayload = () => ({
    baseline_medicines: baselineMeds
      .filter((m) => m.name.trim())
      .map((m) => ({ name: m.name.trim(), dose: cleanNum(m.dose), unit: m.unit || 'mg' })),
    patient: {
      age: cleanNum(patient.age),
      weight_kg: cleanNum(patient.weight_kg),
      gender: patient.gender || null,
      pregnant: !!patient.pregnant,
      renal_disease: patient.renal_disease || 'none',
      hepatic_disease: patient.hepatic_disease || 'none',
      allergies,
      symptoms,
    },
    scenarios: scenarios.map((sc) => ({
      name: sc.name,
      medicine_changes: sc.medicine_changes
        .filter((c) => c.action)
        .map((c) => ({
          action: c.action,
          target: c.target || null,
          name: c.name || null,
          dose: cleanNum(c.dose),
          unit: c.unit || null,
        })),
      patient_changes: normPatientChange(sc.patient_changes),
    })),
    include_rag: includeRag,
    persist: true,
    use_cache: true,
  })

  const normPatientChange = (pc) => {
    if (!pc) return null
    const out = {}
    if (pc.pregnant !== undefined) out.pregnant = pc.pregnant
    if (pc.renal_disease && pc.renal_disease !== 'none') out.renal_disease = pc.renal_disease
    if (pc.hepatic_disease && pc.hepatic_disease !== 'none') out.hepatic_disease = pc.hepatic_disease
    if (pc.age) out.age = Number(pc.age)
    if (pc.weight_kg) out.weight_kg = Number(pc.weight_kg)
    return Object.keys(out).length ? out : null
  }

  const run = async () => {
    if (!baselineNames.length && !symptoms.length) {
      toast.error('Add at least one baseline medicine or a symptom.')
      return
    }
    setLoading(true)
    try {
      const data = await runSimulation(buildPayload())
      setReport(data)
      refreshHistory()
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
    } catch (err) {
      toast.error(errorMessage(err, 'Simulation failed. Is the backend running?'))
    } finally {
      setLoading(false)
    }
  }

  const openHistory = async (id) => {
    setLoading(true)
    try {
      setReport(await getSimulationReport(id))
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load that simulation.'))
    } finally {
      setLoading(false)
    }
  }

  const allResults = report ? [report.baseline, ...report.results] : []
  const recommendedId = report?.recommended_scenario_id

  return (
    <div className="grid gap-6 xl:grid-cols-5">
      {/* ---- Builder panel ---- */}
      <div className="space-y-4 xl:col-span-2">
        <Card className="xl:sticky xl:top-24">
          <CardHeader icon={FlaskConical} title="Treatment Simulator" subtitle="Simulate treatment & patient changes before deciding" />

          {/* Current treatment */}
          <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground"><Pill size={15} className="text-primary" /> Current Treatment</p>
          <MedicineEditor value={baselineMeds} onChange={setBaselineMeds} />

          {/* Patient */}
          <p className="mb-2 mt-5 flex items-center gap-1.5 text-sm font-semibold text-foreground"><User size={15} className="text-primary" /> Patient</p>
          <div className="grid grid-cols-3 gap-2">
            <input className={inputCls} placeholder="Age" value={patient.age} onChange={(e) => setPatient({ ...patient, age: e.target.value })} />
            <input className={inputCls} placeholder="Weight kg" value={patient.weight_kg} onChange={(e) => setPatient({ ...patient, weight_kg: e.target.value })} />
            <select className={inputCls} value={patient.gender} onChange={(e) => setPatient({ ...patient, gender: e.target.value })}>
              <option value="">Gender</option><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option>
            </select>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <label className="flex items-center gap-1"><input type="checkbox" checked={patient.pregnant} onChange={(e) => setPatient({ ...patient, pregnant: e.target.checked })} /> Pregnant</label>
            <label className="flex items-center gap-1">Renal
              <select className={`${inputCls} h-8 w-24`} value={patient.renal_disease} onChange={(e) => setPatient({ ...patient, renal_disease: e.target.value })}>
                {ORGAN_OPTS.map((o) => <option key={o}>{o}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-1">Hepatic
              <select className={`${inputCls} h-8 w-24`} value={patient.hepatic_disease} onChange={(e) => setPatient({ ...patient, hepatic_disease: e.target.value })}>
                {ORGAN_OPTS.map((o) => <option key={o}>{o}</option>)}
              </select>
            </label>
          </div>
          <div className="mt-3 space-y-3">
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-muted">Allergies</p>
              <TagInput value={allergies} onChange={setAllergies} placeholder="e.g. penicillin…" />
            </div>
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-muted">Symptoms</p>
              <TagInput value={symptoms} onChange={setSymptoms} suggestions={symptomOptions} placeholder="e.g. fever, cough…" />
            </div>
          </div>

          {/* Scenarios */}
          <div className="mt-5 flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground"><GitCompareArrows size={15} className="text-primary" /> Scenarios</p>
            <Button size="sm" variant="secondary" onClick={addScenario}><Plus size={14} /> Scenario</Button>
          </div>
          <div className="mt-2 space-y-2">
            {scenarios.map((sc, i) => (
              <ScenarioEditor
                key={i}
                scenario={sc}
                baselineNames={baselineNames}
                onChange={(next) => setScenarios((s) => s.map((x, idx) => (idx === i ? next : x)))}
                onRemove={() => setScenarios((s) => s.filter((_, idx) => idx !== i))}
              />
            ))}
            {scenarios.length === 0 && <p className="text-xs text-muted">Add a scenario to compare against the current treatment.</p>}
          </div>

          <label className="mt-4 flex items-center gap-2 text-sm text-foreground">
            <input type="checkbox" checked={includeRag} onChange={(e) => setIncludeRag(e.target.checked)} />
            Retrieve knowledge-base evidence (RAG)
          </label>

          <div className="mt-3 flex gap-2">
            <Button className="flex-1" onClick={run} loading={loading}><Sparkles size={16} /> Run Simulation</Button>
            <Button variant="secondary" onClick={() => setReport(null)} aria-label="Clear result"><RotateCcw size={16} /></Button>
          </div>

          {history.length > 0 && (
            <div className="mt-5 border-t border-border pt-4">
              <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground"><HistoryIcon size={15} className="text-primary" /> Recent simulations</p>
              <div className="space-y-2">
                {history.map((h) => (
                  <button key={h.id} onClick={() => openHistory(h.id)} className="flex w-full items-center gap-2 rounded-xl border border-border bg-surface p-2.5 text-left transition-colors hover:bg-surface-2">
                    <FlaskConical size={15} className="shrink-0 text-primary" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">{h.top_disease ? titleCase(h.top_disease) : `${h.medicine_count} medicine(s)`}</p>
                      <p className="truncate text-[11px] text-muted">{formatDate(h.created_at)} · {h.scenario_count} scenario(s)</p>
                    </div>
                    <Badge tone={RISK_TONE[h.baseline_risk] || 'neutral'}>{titleCase(h.baseline_risk)}</Badge>
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* ---- Result panel ---- */}
      <div ref={resultRef} className="space-y-5 xl:col-span-3">
        {report ? (
          <>
            {/* Clinical summary + recommendation */}
            <Card className="animate-fade-up border-primary/30 bg-gradient-to-br from-primary-soft/50 to-surface">
              <div className="flex items-start gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground"><Trophy size={22} /></span>
                <div>
                  <h2 className="font-bold text-foreground">Simulation Result</h2>
                  <p className="mt-1 text-sm text-foreground/90">{report.summary}</p>
                  {report.cached && <p className="mt-1 text-xs text-muted">Served from cache</p>}
                </div>
              </div>
            </Card>

            {/* Scenario results grid */}
            <div className="grid gap-4 md:grid-cols-2">
              {allResults.map((res) => (
                <ScenarioResultCard key={res.scenario_id} result={res} recommended={res.scenario_id === recommendedId} />
              ))}
            </div>

            {/* Comparisons (A vs Baseline / A vs B) */}
            {report.comparisons?.length > 0 && (
              <Card className="animate-fade-up">
                <CardHeader icon={GitCompareArrows} title="Scenario Comparison" subtitle="Every variant vs the baseline (and A vs B)" />
                <div className="space-y-2">
                  {report.comparisons.map((c, i) => (
                    <div key={i} className="rounded-xl border border-border bg-surface p-3">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="font-medium text-foreground">{c.to_scenario_name}</span>
                        <ArrowRight size={14} className="text-muted" />
                        <span className="text-muted">{c.from_scenario_name}</span>
                        <Badge tone={c.safer ? 'success' : c.risk_score_delta > 1 ? 'danger' : 'neutral'} className="ml-auto">
                          {c.risk_score_delta > 0 ? '+' : ''}{c.risk_score_delta} risk
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted">{c.verdict}</p>
                      {(c.new_interactions?.length > 0 || c.new_contraindications?.length > 0) && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {c.new_contraindications.map((n) => <Badge key={n} tone="danger"><TriangleAlert size={11} /> {titleCase(n)}</Badge>)}
                          {c.new_interactions.map((n) => <Badge key={n} tone="warning">+ {n}</Badge>)}
                          {c.resolved_interactions.map((n) => <Badge key={n} tone="success">− {n}</Badge>)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Detail for the recommended (or baseline) scenario */}
            <ScenarioDetail result={allResults.find((r) => r.scenario_id === recommendedId) || report.baseline} />
          </>
        ) : (
          <EmptyState
            icon={FlaskConical}
            title="Your simulation result will appear here"
            description="Set the current treatment and patient, add one or more what-if scenarios (dose changes, replace/remove/add, or patient changes like pregnancy or renal impairment), then run the simulation. Every scenario is compared against the baseline."
          />
        )}
      </div>
    </div>
  )
}

// ---------- Detailed breakdown for one scenario ----------
function ScenarioDetail({ result }) {
  if (!result) return null
  return (
    <Card className="animate-fade-up">
      <CardHeader icon={ClipboardCheck} title={`Detail — ${result.scenario_name}`} subtitle="Recommendations, treatment suggestions, evidence & confidence" />

      {/* Clinical recommendations */}
      {result.clinical_recommendations?.length > 0 && (
        <div className="mb-4">
          <p className="mb-2 text-sm font-semibold text-foreground">Clinical Recommendations</p>
          <div className="space-y-2">
            {result.clinical_recommendations.map((r, i) => (
              <div key={i} className="rounded-xl border border-border bg-surface p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">{r.title}</span>
                  <Badge tone={RISK_TONE[r.priority] || 'neutral'}>{titleCase(r.priority)}</Badge>
                </div>
                {r.detail && <p className="mt-0.5 text-xs text-muted">{r.detail}</p>}
                {r.rationale && <p className="mt-0.5 text-xs italic text-muted/80">Why: {r.rationale}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Treatment suggestions (alternatives) */}
      {result.treatment_suggestions?.length > 0 && (
        <div className="mb-4">
          <p className="mb-2 text-sm font-semibold text-foreground">Treatment Suggestions & Alternatives</p>
          <div className="space-y-2">
            {result.treatment_suggestions.map((t, i) => (
              <div key={i} className="rounded-xl border border-border bg-surface p-3">
                <p className="text-sm font-medium text-foreground">{t.suggestion}</p>
                {t.rationale && <p className="text-xs text-muted">Why: {t.rationale}</p>}
                {t.caution && <p className="mt-0.5 text-xs text-warning">Caution: {t.caution}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Side effects */}
      {result.side_effects?.length > 0 && (
        <div className="mb-4">
          <p className="mb-2 text-sm font-semibold text-foreground">Possible Side Effects</p>
          <div className="flex flex-wrap gap-1.5">
            {result.side_effects.map((s, i) => (
              <Badge key={i} tone={s.likelihood === 'common' ? 'warning' : 'neutral'}>
                {titleCase(s.medicine)}: {s.effect}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Evidence cards */}
      {result.evidence?.length > 0 && (
        <div className="mb-4">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground"><BookOpen size={15} className="text-primary" /> Evidence Cards</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {result.evidence.map((e) => (
              <div key={e.id} className="rounded-xl border border-border bg-surface p-3">
                <div className="flex items-start justify-between gap-2">
                  <h4 className="text-sm font-semibold text-foreground">{e.title}</h4>
                  {e.relevance > 0 && <Badge tone="primary">{Math.round(e.relevance * 100)}%</Badge>}
                </div>
                {e.source && <p className="mt-0.5 text-[11px] text-muted">{e.source}</p>}
                {e.snippet && <p className="mt-1.5 text-xs text-muted">{e.snippet}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Confidence meter */}
      <div>
        <p className="mb-2 text-sm font-semibold text-foreground">Confidence</p>
        <ConfidenceMeter breakdown={result.confidence} />
      </div>
    </Card>
  )
}
