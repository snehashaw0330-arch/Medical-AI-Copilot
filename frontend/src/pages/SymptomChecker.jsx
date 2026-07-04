import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  ActivitySquare,
  Activity,
  AlertTriangle,
  Siren,
  Stethoscope,
  FlaskConical,
  HeartHandshake,
  ShieldAlert,
  BookOpen,
  Info,
  History,
  ChevronDown,
  Search,
  Clock,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import ConfidenceBar from '@/ui/ConfidenceBar'
import TagInput from '@/ui/TagInput'
import EmptyState from '@/ui/EmptyState'
import { CardSkeleton } from '@/ui/Skeleton'
import {
  getSymptomCatalog,
  analyzeSymptoms,
  getSymptomHistory,
} from '@/lib/api'
import { errorMessage, titleCase, formatDate } from '@/lib/utils'

// Urgency grade → UI treatment (Requirement 5 & 10).
const URGENCY = {
  self_care: { label: 'Self Care', tone: 'success', color: 'var(--success)', ring: 'border-success/30 bg-success/5', icon: HeartHandshake },
  visit_clinic: { label: 'Visit Clinic', tone: 'primary', color: 'var(--primary)', ring: 'border-primary/30 bg-primary/5', icon: Stethoscope },
  urgent_care: { label: 'Urgent Care', tone: 'warning', color: 'var(--warning)', ring: 'border-warning/30 bg-warning/5', icon: ShieldAlert },
  emergency: { label: 'Emergency', tone: 'danger', color: 'var(--danger)', ring: 'border-danger/40 bg-danger/5', icon: Siren },
}
const urg = (u) => URGENCY[u] || URGENCY.self_care

const SEVERITY_TONE = { mild: 'success', moderate: 'warning', severe: 'danger' }

function band(pct) {
  if (pct > 70) return { label: 'High', tone: 'success' }
  if (pct >= 40) return { label: 'Medium', tone: 'warning' }
  return { label: 'Low', tone: 'danger' }
}

// A single collapsible category of selectable symptom chips (Requirements 2 & 3).
function CategorySection({ category, selectedSet, onToggle }) {
  const [open, setOpen] = useState(false)
  const selectedCount = category.symptoms.filter((s) => selectedSet.has(s)).length
  return (
    <div className="rounded-xl border border-border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
          {category.label}
          {selectedCount > 0 && <Badge tone="primary">{selectedCount}</Badge>}
        </span>
        <ChevronDown size={16} className={`shrink-0 text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="flex flex-wrap gap-1.5 border-t border-border p-3">
          {category.symptoms.map((s) => {
            const active = selectedSet.has(s)
            return (
              <button
                key={s}
                type="button"
                onClick={() => onToggle(s)}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                  active
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-surface text-foreground hover:border-primary/50 hover:bg-primary-soft hover:text-primary'
                }`}
              >
                {titleCase(s)}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function ListCard({ icon: Icon, title, items, empty }) {
  if (!items?.length) return empty ? <p className="text-sm text-muted">{empty}</p> : null
  return (
    <div>
      <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon size={15} className="text-primary" /> {title}
      </p>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-sm text-foreground">
            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function SymptomChecker() {
  const [catalog, setCatalog] = useState(null)
  const [selected, setSelected] = useState([])
  const [severity, setSeverity] = useState(5)
  const [duration, setDuration] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState([])

  const refreshHistory = () => {
    getSymptomHistory({ page: 1, page_size: 5 })
      .then((d) => setHistory(d.items || []))
      .catch(() => {}) // history is non-critical
  }

  // Load the categorized catalog + recent server-side history once.
  useEffect(() => {
    getSymptomCatalog()
      .then(setCatalog)
      .catch(() => toast.error('Could not load the symptom catalog. Is the API running?'))
    refreshHistory()
  }, [])

  const allSymptoms = useMemo(
    () => (catalog?.categories || []).flatMap((c) => c.symptoms),
    [catalog],
  )
  const selectedSet = useMemo(() => new Set(selected), [selected])

  const toggle = (s) =>
    setSelected((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]))

  const analyze = async () => {
    if (selected.length === 0) {
      toast.error('Add at least one symptom')
      return
    }
    setLoading(true)
    try {
      const data = await analyzeSymptoms({
        symptoms: selected,
        severity,
        duration: duration || null,
        include_rag: true,
        top_k: 5,
        persist: true,
      })
      setResult(data)
      refreshHistory()
    } catch (err) {
      toast.error(errorMessage(err, 'Symptom analysis failed'))
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setSelected([])
    setSeverity(5)
    setDuration('')
    setResult(null)
  }

  const conditions = result?.possible_conditions ?? []
  const redFlags = result?.red_flags ?? []

  return (
    <div className="space-y-5">
      {/* Persistent educational disclaimer */}
      <div className="flex items-start gap-3 rounded-2xl border border-primary/20 bg-primary-soft/50 px-4 py-3">
        <Info size={18} className="mt-0.5 shrink-0 text-primary" />
        <p className="text-sm text-foreground">
          <span className="font-semibold">Educational triage aid only.</span> This
          symptom checker does <span className="font-semibold">not</span> provide a
          diagnosis. If you think this could be an emergency, call your local
          emergency number immediately.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* ---------------- Input panel ---------------- */}
        <div className="space-y-6 lg:col-span-2">
          <Card className="lg:sticky lg:top-24">
            <CardHeader
              icon={ActivitySquare}
              title="Symptom Checker"
              subtitle="Search or pick symptoms, then generate an assessment"
            />

            {/* Symptom search + multi-select chips */}
            <TagInput
              value={selected}
              onChange={setSelected}
              suggestions={allSymptoms}
              placeholder="Search symptoms e.g. cough, chest pain"
              disabled={loading}
            />

            {/* Categorized symptom picker */}
            <div className="mt-4">
              <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
                <Search size={13} /> Browse by category
              </p>
              <div className="max-h-72 space-y-2 overflow-auto pr-1">
                {(catalog?.categories || []).map((c) => (
                  <CategorySection key={c.key} category={c} selectedSet={selectedSet} onToggle={toggle} />
                ))}
              </div>
            </div>

            {/* Severity slider */}
            <div className="mt-5">
              <div className="flex items-center justify-between">
                <label htmlFor="severity" className="text-sm font-semibold text-foreground">
                  Severity
                </label>
                <span className="text-sm font-bold" style={{ color: 'var(--primary)' }}>{severity}/10</span>
              </div>
              <input
                id="severity"
                type="range"
                min={1}
                max={10}
                value={severity}
                onChange={(e) => setSeverity(Number(e.target.value))}
                disabled={loading}
                className="mt-2 w-full accent-[var(--primary)]"
              />
              <div className="flex justify-between text-[11px] text-muted">
                <span>Mild</span><span>Moderate</span><span>Severe</span>
              </div>
            </div>

            {/* Duration selector */}
            <div className="mt-4">
              <label htmlFor="duration" className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                <Clock size={14} className="text-muted" /> How long have you had these symptoms?
              </label>
              <select
                id="duration"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                disabled={loading}
                className="mt-2 h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary"
              >
                <option value="">Select duration (optional)</option>
                {(catalog?.durations || []).map((d) => (
                  <option key={d.key} value={d.key}>{d.label}</option>
                ))}
              </select>
            </div>

            <div className="mt-5 flex gap-2">
              <Button className="flex-1" onClick={analyze} loading={loading} disabled={selected.length === 0}>
                <Activity size={16} /> Generate Assessment
              </Button>
              {selected.length > 0 && (
                <Button variant="ghost" onClick={reset} disabled={loading}>Clear</Button>
              )}
            </div>
            <p className="mt-3 text-xs text-muted">Tip: add 3+ symptoms for a more specific assessment.</p>
          </Card>

          {/* Recent assessments (server history) */}
          {history.length > 0 && (
            <Card>
              <CardHeader icon={History} title="Recent assessments" />
              <ul className="space-y-2">
                {history.map((h) => (
                  <li key={h.id} className="flex items-center justify-between gap-2 rounded-xl bg-surface-2 p-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">
                        {h.top_condition || `${h.symptom_count} symptom(s)`}
                      </p>
                      <p className="text-xs text-muted">{formatDate(h.created_at)}</p>
                    </div>
                    <Badge tone={urg(h.urgency_level).tone}>{urg(h.urgency_level).label}</Badge>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        {/* ---------------- Results panel ---------------- */}
        <div className="space-y-4 lg:col-span-3">
          {loading && (<><CardSkeleton /><CardSkeleton /></>)}

          {!loading && !result && (
            <EmptyState
              icon={ActivitySquare}
              title="Your triage assessment will appear here"
              description="Pick your symptoms, set severity and duration, then generate an assessment to see possible conditions, urgency level, the right specialist and evidence-based guidance."
            />
          )}

          {!loading && result && (
            <>
              {/* Emergency warning banner (Requirement 4) */}
              {result.emergency_warning && (
                <Card className="border-danger/40 bg-danger/5">
                  <div className="flex items-start gap-3">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-danger/15 text-danger">
                      <Siren size={24} />
                    </span>
                    <div>
                      <h3 className="text-base font-bold text-danger">Emergency warning</h3>
                      <p className="mt-1 text-sm text-foreground">{result.emergency_warning}</p>
                    </div>
                  </div>
                </Card>
              )}

              {/* Triage summary (urgency + severity + specialist) */}
              {(() => {
                const cfg = urg(result.urgency_level)
                const Icon = cfg.icon
                return (
                  <Card className={cfg.ring}>
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <span className="grid h-12 w-12 place-items-center rounded-2xl" style={{ backgroundColor: `${cfg.color}1a`, color: cfg.color }}>
                          <Icon size={26} />
                        </span>
                        <div>
                          <p className="text-xs text-muted">Recommended action</p>
                          <h2 className="text-xl font-bold" style={{ color: cfg.color }}>{result.urgency_label}</h2>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone={SEVERITY_TONE[result.severity_level] || 'neutral'}>
                          {titleCase(result.severity_level)} severity
                        </Badge>
                        <div className="text-right">
                          <p className="text-xs text-muted">Triage score</p>
                          <p className="text-lg font-bold" style={{ color: cfg.color }}>{Math.round(result.triage_score)}</p>
                        </div>
                      </div>
                    </div>
                    <p className="mt-3 text-sm text-foreground">{result.urgency_description}</p>
                    <div className="mt-4 flex items-center gap-2 rounded-xl bg-surface-2 p-3">
                      <Stethoscope size={18} className="shrink-0 text-primary" />
                      <p className="text-sm text-foreground">
                        <span className="font-semibold">See a: </span>{result.recommended_specialist}
                      </p>
                    </div>
                  </Card>
                )
              })()}

              {/* Red flags (Requirement 4) */}
              {redFlags.length > 0 && (
                <Card className="border-warning/30 bg-warning/5">
                  <CardHeader icon={AlertTriangle} title="Red-flag symptoms" subtitle="These warrant closer attention" />
                  <ul className="space-y-2">
                    {redFlags.map((f, i) => (
                      <li key={i} className="flex items-start gap-2 rounded-xl bg-surface p-3">
                        <ShieldAlert size={16} className={`mt-0.5 shrink-0 ${f.emergency ? 'text-danger' : 'text-warning'}`} />
                        <div>
                          <p className="text-sm font-semibold text-foreground">
                            {titleCase(f.symptom)}
                            {f.emergency && <Badge tone="danger" className="ml-2">Emergency</Badge>}
                          </p>
                          <p className="text-sm text-muted">{f.reason}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {/* Possible conditions (Requirement 10) */}
              <Card>
                <CardHeader icon={Stethoscope} title="Possible Conditions" subtitle="Ranked by the prediction model — not a diagnosis" />
                {conditions.length === 0 ? (
                  <p className="text-sm text-muted">
                    No specific conditions were matched. {result.warnings?.[0] || 'Try adding more symptoms.'}
                  </p>
                ) : (
                  <div className="space-y-3">
                    {conditions.map((c, i) => {
                      const b = band(c.confidence)
                      return (
                        <div key={i} className="rounded-xl bg-surface-2 p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-center gap-3">
                              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary-soft text-sm font-bold text-primary">#{i + 1}</span>
                              <h3 className="font-semibold text-foreground">{c.disease}</h3>
                            </div>
                            <div className="flex shrink-0 flex-col items-end gap-1">
                              <span className="text-sm font-bold text-foreground">{c.confidence.toFixed(1)}%</span>
                              <Badge tone={b.tone}>{b.label}</Badge>
                            </div>
                          </div>
                          <div className="mt-3"><ConfidenceBar value={c.confidence} showLabel={false} /></div>
                          {c.explanation && <p className="mt-2 text-sm text-muted">{c.explanation}</p>}
                        </div>
                      )
                    })}
                  </div>
                )}
                {result.confidence_level && (
                  <p className="mt-3 text-xs text-muted">
                    Overall model confidence: <span className="font-medium text-foreground">{titleCase(result.confidence_level)}</span>
                  </p>
                )}
              </Card>

              {/* Recommended actions: tests + home care (Requirement 4) */}
              <Card>
                <CardHeader icon={HeartHandshake} title="Recommended actions" />
                <div className="grid gap-5 sm:grid-cols-2">
                  <ListCard icon={FlaskConical} title="Recommended tests" items={result.recommended_tests} />
                  <ListCard icon={HeartHandshake} title="Home care" items={result.home_care} />
                </div>
              </Card>

              {/* Evidence-based references from RAG (Requirements 6 & 10) */}
              {(result.rag_explanation || result.related_documents?.length > 0) && (
                <Card>
                  <CardHeader icon={BookOpen} title="From the knowledge base" subtitle="Evidence-based context retrieved by RAG" />
                  {result.rag_explanation && (
                    <p className="whitespace-pre-wrap text-sm text-foreground">{result.rag_explanation}</p>
                  )}
                  {result.related_documents?.length > 0 && (
                    <div className="mt-4 space-y-2">
                      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Related documents</p>
                      {result.related_documents.map((d, i) => (
                        <div key={i} className="rounded-xl bg-surface-2 p-3">
                          <p className="flex items-center gap-1.5 text-xs font-semibold text-primary">
                            <BookOpen size={13} /> {d.source}
                          </p>
                          {d.excerpt && <p className="mt-1 line-clamp-3 text-sm text-muted">{d.excerpt}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                  {result.rag_sources?.length > 0 && (
                    <p className="mt-3 text-xs text-muted">
                      <span className="font-medium text-foreground">Sources: </span>{result.rag_sources.join(', ')}
                    </p>
                  )}
                </Card>
              )}

              {/* Unmatched symptoms note */}
              {result.unmatched_symptoms?.length > 0 && (
                <Card>
                  <h4 className="mb-2 text-sm font-semibold text-foreground">Unrecognised symptoms</h4>
                  <div className="flex flex-wrap gap-1.5">
                    {result.unmatched_symptoms.map((u) => <Badge key={u} tone="danger">{u}</Badge>)}
                  </div>
                  <p className="mt-2 text-xs text-muted">These weren’t found in our catalog and were not used in the assessment.</p>
                </Card>
              )}

              {result.disclaimer && (
                <p className="px-2 text-center text-xs text-muted">{result.disclaimer}</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
