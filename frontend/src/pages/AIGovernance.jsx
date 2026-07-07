import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import {
  ShieldCheck, Activity, Gauge, Timer, XCircle, AlertTriangle, TrendingDown,
  RefreshCw, Search, Stethoscope, Pill, FileText, Download, Layers,
  Cpu, Database, GitBranch, BookOpen, X, Sparkles, ScrollText,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import { CardSkeleton } from '@/ui/Skeleton'
import {
  getGovernanceDashboard, getGovernanceVersions, syncGovernance, searchDecisions,
  getDecisionTrace, getDecisionExplanation, getDecisionConfidence,
  governanceExportUrl,
} from '@/lib/api'
import { errorMessage, titleCase, formatDate, confidenceColor } from '@/lib/utils'

const STATUS_TONE = {
  success: 'success', partial: 'warning', low_confidence: 'warning', failed: 'danger',
}
const RELIABILITY_TONE = {
  high: 'success', moderate: 'primary', low: 'warning', unreliable: 'danger',
}
const statusTone = (s) => STATUS_TONE[s] || 'neutral'

function Stat({ icon: Icon, label, value, tone = 'primary', sub }) {
  return (
    <Card className="flex items-center gap-3">
      <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-${tone}-soft`}
        style={{ background: 'var(--primary-soft)' }}>
        <Icon size={20} className="text-primary" />
      </span>
      <div className="min-w-0">
        <p className="truncate text-xs uppercase tracking-wide text-muted">{label}</p>
        <p className="text-xl font-bold text-foreground">{value}</p>
        {sub && <p className="text-xs text-muted">{sub}</p>}
      </div>
    </Card>
  )
}

// Horizontal ranked bar list (diseases / medicines).
function RankedList({ items, color = 'var(--primary)' }) {
  const max = Math.max(1, ...items.map((i) => i.count))
  if (!items.length) return <p className="text-sm text-muted">No data yet.</p>
  return (
    <ul className="space-y-2">
      {items.map((it) => (
        <li key={it.name}>
          <div className="flex items-center justify-between text-sm">
            <span className="truncate text-foreground">{titleCase(it.name)}</span>
            <span className="ml-2 shrink-0 font-semibold text-muted">{it.count}</span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full" style={{ width: `${(it.count / max) * 100}%`, background: color }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

function VersionChip({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-2 rounded-xl bg-surface-2 px-3 py-2">
      <Icon size={15} className="shrink-0 text-primary" />
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wide text-muted">{label}</p>
        <p className="truncate text-xs font-semibold text-foreground">{value || '—'}</p>
      </div>
    </div>
  )
}

// Explainability list block.
function WhyBlock({ title, icon: Icon, items, tone = 'neutral', empty }) {
  if (!items?.length) return empty ? <p className="text-sm text-muted">{empty}</p> : null
  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
        <Icon size={13} className="text-primary" /> {title}
      </p>
      <ul className="space-y-2">
        {items.map((it, i) => (
          <li key={i} className="rounded-xl bg-surface-2 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-foreground">{it.subject}</span>
              <Badge tone={tone}>{titleCase(it.decision)}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted">{it.rationale}</p>
            {it.evidence?.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {it.evidence.map((e, j) => (
                  <span key={j} className="rounded-md bg-background px-1.5 py-0.5 text-[11px] text-muted">{e}</span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

// The slide-in decision detail: trace + explainability + confidence.
function DecisionDetail({ traceId, onClose }) {
  const [trace, setTrace] = useState(null)
  const [explain, setExplain] = useState(null)
  const [conf, setConf] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    Promise.all([
      getDecisionTrace(traceId), getDecisionExplanation(traceId), getDecisionConfidence(traceId),
    ])
      .then(([t, e, c]) => { if (alive) { setTrace(t); setExplain(e); setConf(c) } })
      .catch((err) => toast.error(errorMessage(err, 'Could not load the decision')))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [traceId])

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-full max-w-2xl overflow-y-auto bg-background p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold text-foreground">
              <ShieldCheck size={20} className="text-primary" /> Decision Trace
            </h2>
            <p className="font-mono text-xs text-muted">{traceId}</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-surface-2"><X size={20} /></button>
        </div>

        {loading && <CardSkeleton />}

        {!loading && trace && (
          <div className="space-y-4">
            {/* headline */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Card className="p-3">
                <p className="text-[10px] uppercase tracking-wide text-muted">Confidence</p>
                <p className="text-lg font-bold" style={{ color: confidenceColor((trace.confidence || 0) * 100) }}>
                  {Math.round((trace.confidence || 0) * 100)}%
                </p>
              </Card>
              <Card className="p-3">
                <p className="text-[10px] uppercase tracking-wide text-muted">Status</p>
                <Badge tone={statusTone(trace.status)}>{titleCase(trace.status)}</Badge>
              </Card>
              <Card className="p-3">
                <p className="text-[10px] uppercase tracking-wide text-muted">Exec time</p>
                <p className="text-lg font-bold text-foreground">{(trace.execution_time || 0).toFixed(2)}s</p>
              </Card>
              <Card className="p-3">
                <p className="text-[10px] uppercase tracking-wide text-muted">Medicines</p>
                <p className="text-lg font-bold text-foreground">{trace.medicines?.length || 0}</p>
              </Card>
            </div>

            {/* confidence analysis */}
            {conf && (
              <Card>
                <CardHeader icon={Gauge} title="Confidence Analysis"
                  action={<Badge tone={RELIABILITY_TONE[conf.reliability] || 'neutral'}>{titleCase(conf.reliability)} · {Math.round(conf.reliability_score)}/100</Badge>} />
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[['Calibration', conf.calibration], ['Evidence', conf.evidence_strength],
                    ['Uncertainty', conf.model_uncertainty], ['Confidence', conf.confidence]].map(([l, v]) => (
                    <div key={l}>
                      <div className="flex justify-between text-xs"><span className="text-muted">{l}</span>
                        <span className="font-semibold text-foreground">{Math.round((v || 0) * 100)}%</span></div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                        <div className="h-full rounded-full bg-primary" style={{ width: `${(v || 0) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-sm text-foreground">{conf.summary}</p>
                {conf.missing_information?.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {conf.missing_information.map((m, i) => (
                      <li key={i} className="flex gap-2 text-xs text-muted"><AlertTriangle size={12} className="mt-0.5 shrink-0 text-warning" />{m}</li>
                    ))}
                  </ul>
                )}
              </Card>
            )}

            {/* explainability */}
            {explain && (
              <Card className="space-y-4">
                <CardHeader icon={Sparkles} title="Explainability" subtitle={explain.summary} />
                <WhyBlock title="Why these medicines" icon={Pill} items={explain.medicine_matching} tone="primary" />
                <WhyBlock title="Why this disease was chosen" icon={Stethoscope} items={explain.disease_selected} tone="success" />
                <WhyBlock title="Why other diseases were rejected" icon={Stethoscope} items={explain.disease_rejected} tone="neutral" />
                <WhyBlock title="Why interactions were flagged" icon={AlertTriangle} items={explain.drug_interactions} tone="danger" />
                <WhyBlock title="Why these documents were retrieved" icon={BookOpen} items={explain.rag_retrieval} tone="primary" />
                <WhyBlock title="Why the recommendation was generated" icon={FileText} items={explain.final_recommendation} tone="success" />
              </Card>
            )}

            {/* provenance */}
            <Card>
              <CardHeader icon={GitBranch} title="Provenance & Versions" />
              <div className="grid gap-2 sm:grid-cols-2">
                <VersionChip icon={Cpu} label="Model" value={trace.versions?.model_version} />
                <VersionChip icon={Database} label="Dataset" value={trace.versions?.dataset_version} />
                <VersionChip icon={ScrollText} label="Prompt" value={trace.versions?.prompt_version} />
                <VersionChip icon={GitBranch} label="Pipeline" value={trace.versions?.pipeline_version} />
              </div>
              <div className="mt-3">
                <Link to={`/governance/pipeline?trace=${encodeURIComponent(traceId)}`}
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
                  <Layers size={15} /> View pipeline execution
                </Link>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}

export default function AIGovernance() {
  const [dash, setDash] = useState(null)
  const [versions, setVersions] = useState(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [decisions, setDecisions] = useState([])
  const [query, setQuery] = useState({ patient: '', medicine: '', disease: '' })
  const [selected, setSelected] = useState(null)

  const loadDash = async () => {
    setLoading(true)
    try {
      const [d, v] = await Promise.all([getGovernanceDashboard(), getGovernanceVersions()])
      setDash(d); setVersions(v)
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load governance dashboard'))
    } finally { setLoading(false) }
  }

  const loadDecisions = async () => {
    try {
      const page = await searchDecisions({ ...query, page_size: 25 })
      setDecisions(page.items || [])
    } catch (err) {
      toast.error(errorMessage(err, 'Search failed'))
    }
  }

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [d, v] = await Promise.all([getGovernanceDashboard(), getGovernanceVersions()])
        if (alive) { setDash(d); setVersions(v) }
      } catch (err) {
        toast.error(errorMessage(err, 'Could not load governance dashboard'))
      } finally { if (alive) setLoading(false) }
      try {
        const p = await searchDecisions({ page_size: 25 })
        if (alive) setDecisions(p.items || [])
      } catch { /* surfaced above */ }
    })()
    return () => { alive = false }
  }, [])

  const sync = async () => {
    setSyncing(true)
    try {
      const res = await syncGovernance()
      toast.success(res.message || 'Synced')
      await loadDash(); await loadDecisions()
    } catch (err) {
      toast.error(errorMessage(err, 'Sync failed'))
    } finally { setSyncing(false) }
  }

  const overTime = useMemo(
    () => (dash?.decisions_over_time || []).map((p) => ({ t: p.date?.slice(5), count: p.count })),
    [dash],
  )

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-foreground">
            <ShieldCheck size={22} className="text-primary" /> AI Governance
          </h1>
          <p className="text-sm text-muted">Every AI decision — explainable, traceable, auditable, reproducible & versioned.</p>
        </div>
        <div className="flex items-center gap-2">
          <a href={governanceExportUrl('decisions', 'csv')} className="inline-flex">
            <Button variant="secondary"><Download size={15} /> Export CSV</Button>
          </a>
          <Button variant="secondary" onClick={sync} loading={syncing}><RefreshCw size={15} /> Sync</Button>
        </div>
      </div>

      {loading && <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><CardSkeleton /><CardSkeleton /><CardSkeleton /></div>}

      {!loading && dash && (
        <>
          {/* KPI grid */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <Stat icon={Activity} label="AI Decisions" value={dash.total_decisions} />
            <Stat icon={Gauge} label="Avg Confidence" value={`${Math.round((dash.average_confidence || 0) * 100)}%`} />
            <Stat icon={Timer} label="Avg Time" value={`${(dash.average_processing_time || 0).toFixed(2)}s`} />
            <Stat icon={XCircle} label="Failed" value={dash.failed_predictions} />
            <Stat icon={AlertTriangle} label="Audit Failures" value={dash.audit_failures} />
            <Stat icon={TrendingDown} label="Low Confidence" value={dash.low_confidence_cases} />
          </div>

          {/* versions */}
          {versions && (
            <Card>
              <CardHeader icon={GitBranch} title="Active Versions" subtitle="Pinned for reproducibility across every decision" />
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                <VersionChip icon={Cpu} label="Model" value={versions.model_version} />
                <VersionChip icon={Database} label="Dataset" value={versions.dataset_version} />
                <VersionChip icon={ScrollText} label="Prompt" value={versions.prompt_version} />
                <VersionChip icon={GitBranch} label="Pipeline" value={versions.pipeline_version} />
                <VersionChip icon={BookOpen} label="RAG Index" value={versions.rag_index_version} />
              </div>
            </Card>
          )}

          {/* charts + rankings */}
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-1">
              <CardHeader icon={Activity} title="Decisions Over Time" />
              {overTime.length < 2 ? <p className="py-8 text-center text-sm text-muted">Not enough data yet.</p> : (
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={overTime} margin={{ top: 5, right: 8, left: -22, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                      <XAxis dataKey="t" stroke="var(--muted)" fontSize={11} tickLine={false} axisLine={false} />
                      <YAxis stroke="var(--muted)" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                      <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, fontSize: 12 }} />
                      <Line type="monotone" dataKey="count" stroke="var(--primary)" strokeWidth={2.5} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
            <Card>
              <CardHeader icon={Stethoscope} title="Most Common Diseases" />
              <RankedList items={dash.most_common_diseases || []} color="var(--primary)" />
            </Card>
            <Card>
              <CardHeader icon={Pill} title="Most Common Medicines" />
              <RankedList items={dash.most_common_medicines || []} color="var(--success)" />
            </Card>
          </div>

          {/* decision search + table */}
          <Card>
            <CardHeader icon={Search} title="AI Decision Traces" subtitle="Search by patient, medicine or disease — click a row to explain" />
            <div className="mb-3 grid gap-2 sm:grid-cols-4">
              {[['patient', 'Patient'], ['medicine', 'Medicine'], ['disease', 'Disease']].map(([k, label]) => (
                <input key={k} placeholder={label} value={query[k]}
                  onChange={(e) => setQuery((q) => ({ ...q, [k]: e.target.value }))}
                  onKeyDown={(e) => e.key === 'Enter' && loadDecisions()}
                  className="h-10 rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary" />
              ))}
              <Button variant="primary" onClick={loadDecisions}><Search size={15} /> Search</Button>
            </div>

            {decisions.length === 0 ? (
              <EmptyState icon={ShieldCheck} title="No decisions traced yet"
                description="Analyse a prescription (Prescription OCR) or press Sync to backfill traces from your existing reports." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                      <th className="py-2 pr-3 font-medium">When</th>
                      <th className="py-2 pr-3 font-medium">Patient</th>
                      <th className="py-2 pr-3 font-medium">Disease</th>
                      <th className="py-2 pr-3 font-medium">Meds</th>
                      <th className="py-2 pr-3 font-medium">Confidence</th>
                      <th className="py-2 pr-3 font-medium">Status</th>
                      <th className="py-2 pr-3 font-medium">Model</th>
                    </tr>
                  </thead>
                  <tbody>
                    {decisions.map((d) => (
                      <tr key={d.trace_id} onClick={() => setSelected(d.trace_id)}
                        className="cursor-pointer border-b border-border/60 hover:bg-surface-2">
                        <td className="py-2.5 pr-3 text-muted">{formatDate(d.created_at)?.split(',')[0]}</td>
                        <td className="py-2.5 pr-3 font-medium text-foreground">{d.patient_name || '—'}</td>
                        <td className="py-2.5 pr-3 text-foreground">{d.top_disease || '—'}</td>
                        <td className="py-2.5 pr-3 text-muted">{d.medicine_count}</td>
                        <td className="py-2.5 pr-3 font-semibold" style={{ color: confidenceColor((d.confidence || 0) * 100) }}>
                          {Math.round((d.confidence || 0) * 100)}%
                        </td>
                        <td className="py-2.5 pr-3"><Badge tone={statusTone(d.status)}>{titleCase(d.status)}</Badge></td>
                        <td className="py-2.5 pr-3 font-mono text-[11px] text-muted">{d.model_version}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {selected && <DecisionDetail traceId={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
