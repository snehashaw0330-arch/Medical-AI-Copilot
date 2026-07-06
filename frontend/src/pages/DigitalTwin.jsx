import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import {
  HeartPulse, Activity, ShieldAlert, TrendingUp, TrendingDown, Minus,
  RefreshCw, Pill, Stethoscope, ClipboardList, Sparkles, BookOpen, Info,
  Gauge, CalendarClock, AlertTriangle,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import { CardSkeleton } from '@/ui/Skeleton'
import {
  getDigitalTwinPatients, getDigitalTwin, recalculateDigitalTwin,
} from '@/lib/api'
import { errorMessage, titleCase, formatDate, confidenceColor } from '@/lib/utils'

const DIR = {
  improving: { tone: 'success', color: 'var(--success)', icon: TrendingUp, label: 'Improving' },
  stable: { tone: 'primary', color: 'var(--primary)', icon: Minus, label: 'Stable' },
  worsening: { tone: 'danger', color: 'var(--danger)', icon: TrendingDown, label: 'Worsening' },
}
const dir = (d) => DIR[d] || DIR.stable

const RISK = {
  low: { tone: 'success', color: 'var(--success)', label: 'Low', pct: 15 },
  medium: { tone: 'warning', color: 'var(--warning)', label: 'Medium', pct: 45 },
  high: { tone: 'danger', color: 'var(--danger)', label: 'High', pct: 75 },
  critical: { tone: 'danger', color: '#b91c1c', label: 'Critical', pct: 95 },
}
const risk = (r) => RISK[r] || RISK.low

// A trend chart driven by polarity/direction colour.
function TrendChart({ trend, unit = '' }) {
  const cfg = dir(trend?.direction)
  const data = (trend?.series || []).map((p) => ({
    t: formatDate(p.timestamp)?.split(',')[0] || '',
    value: Math.round(p.value * 10) / 10,
  }))
  const Icon = cfg.icon
  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">{titleCase(trend?.metric?.replace(/_/g, ' ') || '')}</p>
        <Badge tone={cfg.tone}><Icon size={12} /> {cfg.label}</Badge>
      </div>
      {data.length < 2 ? (
        <p className="py-8 text-center text-sm text-muted">Not enough data points yet.</p>
      ) : (
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="t" stroke="var(--muted)" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="var(--muted)" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, fontSize: 12 }}
                labelStyle={{ color: 'var(--muted)' }}
                formatter={(v) => [`${v}${unit}`, 'Value']}
              />
              <Line type="monotone" dataKey="value" stroke={cfg.color} strokeWidth={2.5} dot={{ r: 3, fill: cfg.color }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {trend?.summary && <p className="mt-1 text-xs text-muted">{trend.summary}</p>}
    </Card>
  )
}

// Circular gauge for the health score.
function HealthGauge({ score }) {
  const pct = Math.max(0, Math.min(100, score || 0))
  const color = confidenceColor(pct)
  const r = 54
  const c = 2 * Math.PI * r
  const off = c * (1 - pct / 100)
  return (
    <div className="relative grid place-items-center">
      <svg width="140" height="140" viewBox="0 0 140 140" className="-rotate-90">
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="12" />
        <circle cx="70" cy="70" r={r} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={off} style={{ transition: 'stroke-dashoffset 0.8s ease' }} />
      </svg>
      <div className="absolute text-center">
        <p className="text-3xl font-bold" style={{ color }}>{Math.round(pct)}</p>
        <p className="text-[11px] uppercase tracking-wide text-muted">Health Score</p>
      </div>
    </div>
  )
}

// Segmented risk meter.
function RiskMeter({ level }) {
  const cfg = risk(level)
  const levels = ['low', 'medium', 'high', 'critical']
  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">Future Risk</p>
        <Badge tone={cfg.tone}>{cfg.label}</Badge>
      </div>
      <div className="mt-3 flex gap-1.5">
        {levels.map((l) => {
          const active = l === level
          const rc = risk(l)
          return (
            <div key={l} className="flex-1">
              <div className="h-2.5 rounded-full" style={{ backgroundColor: active ? rc.color : 'var(--surface-2)' }} />
              <p className="mt-1 text-center text-[10px] font-medium" style={{ color: active ? rc.color : 'var(--muted)' }}>{titleCase(l)}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function FactorBar({ label, value }) {
  const color = confidenceColor(value)
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="font-semibold" style={{ color }}>{Math.round(value)}</span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full" style={{ width: `${value}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}

export default function DigitalTwin() {
  const [patients, setPatients] = useState([])
  const [patientId, setPatientId] = useState('')
  const [twin, setTwin] = useState(null)
  const [loading, setLoading] = useState(false)
  const [recalculating, setRecalculating] = useState(false)

  const load = async (id) => {
    setPatientId(id)
    setLoading(true)
    try {
      setTwin(await getDigitalTwin(id))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not build the digital twin'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    getDigitalTwinPatients()
      .then((list) => {
        setPatients(list)
        if (list.length) load(list[0].patient_id)
      })
      .catch(() => toast.error('Could not load patients. Is the API running?'))
  }, [])

  const recalc = async () => {
    if (!patientId) return
    setRecalculating(true)
    try {
      await recalculateDigitalTwin(patientId)
      await load(patientId)
      toast.success('Digital twin recalculated')
    } catch (err) {
      toast.error(errorMessage(err, 'Recalculation failed'))
    } finally {
      setRecalculating(false)
    }
  }

  const status = dir(twin?.health_status)
  const StatusIcon = status.icon

  const factorRows = useMemo(() => {
    const f = twin?.health_score_breakdown || {}
    return [
      ['Adherence', f.adherence],
      ['Risk level', f.risk],
      ['Disease progression', f.disease_progression],
      ['Drug interactions', f.drug_interactions],
      ['Prediction confidence', f.prediction_confidence],
      ['Clinical warnings', f.clinical_warnings],
    ]
  }, [twin])

  return (
    <div className="space-y-5">
      {/* Header + patient picker */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-foreground">
            <HeartPulse size={22} className="text-primary" /> Digital Twin
          </h1>
          <p className="text-sm text-muted">A living virtual health profile aggregated from every analysis.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={patientId}
            onChange={(e) => load(e.target.value)}
            disabled={loading || !patients.length}
            className="h-10 rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary"
          >
            {!patients.length && <option>No patients yet</option>}
            {patients.map((p) => (
              <option key={p.patient_id} value={p.patient_id}>
                {p.patient_name} ({p.report_count})
              </option>
            ))}
          </select>
          <Button variant="secondary" onClick={recalc} loading={recalculating} disabled={!patientId}>
            <RefreshCw size={15} /> Recalculate
          </Button>
        </div>
      </div>

      <div className="flex items-start gap-3 rounded-2xl border border-primary/20 bg-primary-soft/50 px-4 py-3">
        <Info size={18} className="mt-0.5 shrink-0 text-primary" />
        <p className="text-sm text-foreground">
          The Digital Twin is an automated, aggregated view for <span className="font-semibold">educational support only</span> — not a diagnosis or medical record. Verify all values with a clinician.
        </p>
      </div>

      {loading && (<><CardSkeleton /><CardSkeleton /></>)}

      {!loading && !patients.length && (
        <EmptyState
          icon={HeartPulse}
          title="No patient data yet"
          description="Analyse a prescription (Prescription OCR) to create the first patient record — the Digital Twin builds automatically from your reports."
        />
      )}

      {!loading && twin && twin.report_count === 0 && (
        <EmptyState icon={HeartPulse} title="No analyses on record" description={twin.ai_summary} />
      )}

      {!loading && twin && twin.report_count > 0 && (
        <>
          {/* Headline: gauge, status, risk, prediction */}
          <div className="grid gap-4 lg:grid-cols-4">
            <Card className="flex flex-col items-center justify-center gap-2">
              <HealthGauge score={twin.health_score} />
              <Badge tone={status.tone}><StatusIcon size={12} /> {status.label}</Badge>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader icon={ShieldAlert} title="Risk & Prediction" />
              <RiskMeter level={twin.risk?.level} />
              <div className="mt-4 rounded-xl bg-surface-2 p-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
                  <CalendarClock size={13} className="text-primary" /> Forecast ({twin.prediction?.horizon})
                </p>
                <p className="mt-1 text-sm text-foreground">{twin.prediction?.summary}</p>
                {twin.prediction?.projected_health_score != null && (
                  <div className="mt-2 flex items-center gap-3 text-sm">
                    <span className="text-muted">Projected score:</span>
                    <span className="font-bold" style={{ color: confidenceColor(twin.prediction.projected_health_score) }}>
                      {Math.round(twin.prediction.projected_health_score)}
                    </span>
                    <span className="text-muted">· risk:</span>
                    <Badge tone={risk(twin.prediction.projected_risk).tone}>{risk(twin.prediction.projected_risk).label}</Badge>
                  </div>
                )}
              </div>
              {twin.risk?.drivers?.length > 0 && (
                <ul className="mt-3 space-y-1">
                  {twin.risk.drivers.slice(0, 3).map((d, i) => (
                    <li key={i} className="flex gap-2 text-xs text-muted"><AlertTriangle size={12} className="mt-0.5 shrink-0 text-warning" />{d}</li>
                  ))}
                </ul>
              )}
            </Card>

            <Card>
              <CardHeader icon={Gauge} title="Score factors" />
              <div className="space-y-2.5">
                {factorRows.map(([label, val]) => <FactorBar key={label} label={label} value={val || 0} />)}
              </div>
            </Card>
          </div>

          {/* AI summary */}
          <Card className="border-primary/20 bg-primary-soft/30">
            <CardHeader icon={Sparkles} title="AI Summary" subtitle={`${twin.report_count} analyses · ${formatDate(twin.first_seen)?.split(',')[0]} → ${formatDate(twin.last_seen)?.split(',')[0]}`} />
            <p className="text-sm text-foreground">{twin.ai_summary}</p>
          </Card>

          {/* Charts */}
          <div>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted">
              <Activity size={15} className="text-primary" /> Trends & Charts
            </h2>
            <div className="grid gap-4 lg:grid-cols-2">
              {twin.trends?.health_score && <TrendChart trend={twin.trends.health_score} />}
              {twin.trends?.risk && <TrendChart trend={twin.trends.risk} />}
              {twin.trends?.ocr_quality && <TrendChart trend={twin.trends.ocr_quality} />}
              {twin.trends?.disease && <TrendChart trend={twin.trends.disease} />}
              {twin.trends?.medicine && <TrendChart trend={twin.trends.medicine} />}
            </div>
          </div>

          {/* Medicine + Disease history */}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader icon={Pill} title="Medicine History" />
              {twin.medicines?.length ? (
                <ul className="space-y-2">
                  {twin.medicines.map((m) => (
                    <li key={m.name} className="flex items-center justify-between gap-2 rounded-xl bg-surface-2 p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-foreground">{m.name}</p>
                        <p className="text-xs text-muted">
                          {m.occurrences}× · {m.last_dosage || '—'} · since {formatDate(m.first_seen)?.split(',')[0]}
                        </p>
                      </div>
                      <Badge tone={m.status === 'active' ? 'success' : 'neutral'}>{titleCase(m.status)}</Badge>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted">No medicines on record.</p>}
            </Card>

            <Card>
              <CardHeader icon={Stethoscope} title="Disease Progress" />
              {twin.diseases?.length ? (
                <ul className="space-y-2">
                  {twin.diseases.map((d) => (
                    <li key={d.disease} className="flex items-center justify-between gap-2 rounded-xl bg-surface-2 p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-foreground">{d.disease}</p>
                        <p className="text-xs text-muted">Seen {d.occurrences}× · last {formatDate(d.last_seen)?.split(',')[0]}</p>
                      </div>
                      <Badge tone="primary">{d.occurrences}</Badge>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted">No conditions on record.</p>}
            </Card>
          </div>

          {/* Timeline */}
          <Card>
            <CardHeader icon={ClipboardList} title="Timeline" subtitle="The patient's health journey (newest first)" />
            <ol className="relative space-y-4 border-l border-border pl-5">
              {twin.timeline.slice(0, 20).map((e) => {
                const rl = e.risk_level ? risk(e.risk_level) : null
                return (
                  <li key={e.id} className="relative">
                    <span
                      className="absolute -left-[27px] top-1 grid h-4 w-4 place-items-center rounded-full border-2 border-surface"
                      style={{ backgroundColor: e.type === 'high_risk' ? 'var(--danger)' : e.type === 'new_medicine' ? 'var(--primary)' : 'var(--success)' }}
                    />
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-foreground">{e.title}</p>
                      <span className="text-xs text-muted">{formatDate(e.timestamp)}</span>
                    </div>
                    {e.description && <p className="text-xs text-muted">{e.description}</p>}
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {rl && <Badge tone={rl.tone}>{rl.label} risk</Badge>}
                      {e.confidence != null && <Badge tone="neutral">{Math.round(e.confidence * 100)}% conf</Badge>}
                    </div>
                  </li>
                )
              })}
            </ol>
          </Card>

          {/* Recommendations + evidence */}
          {(twin.recommendations?.length > 0 || twin.evidence?.length > 0) && (
            <Card>
              <CardHeader icon={ClipboardList} title="Recommendations" subtitle="Aggregated from the latest analyses + RAG evidence" />
              {twin.recommendations?.length > 0 && (
                <ul className="space-y-1.5">
                  {twin.recommendations.map((r, i) => (
                    <li key={i} className="flex gap-2 text-sm text-foreground">
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />{r}
                    </li>
                  ))}
                </ul>
              )}
              {twin.evidence?.length > 0 && (
                <div className="mt-4 space-y-2">
                  <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted"><BookOpen size={13} /> Evidence from the knowledge base</p>
                  {twin.evidence.map((ev, i) => (
                    <div key={i} className="rounded-xl bg-surface-2 p-3">
                      <p className="text-xs font-semibold text-primary">{ev.source}</p>
                      {ev.text && <p className="mt-1 line-clamp-3 text-sm text-muted">{ev.text}</p>}
                    </div>
                  ))}
                </div>
              )}
              {twin.rag_sources?.length > 0 && (
                <p className="mt-3 text-xs text-muted"><span className="font-medium text-foreground">Sources: </span>{twin.rag_sources.join(', ')}</p>
              )}
            </Card>
          )}

          <p className="px-2 text-center text-xs text-muted">{twin.disclaimer}</p>
        </>
      )}
    </div>
  )
}
