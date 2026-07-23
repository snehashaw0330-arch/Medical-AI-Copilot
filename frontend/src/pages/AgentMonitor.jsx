import { useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Workflow,
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  MinusCircle,
  Circle,
  Clock,
  Cpu,
  ScrollText,
  ListChecks,
  Activity,
  UploadCloud,
  X,
  ChevronRight,
  Gauge,
  HeartPulse,
  GanttChartSquare,
  History as HistoryIcon,
  RefreshCw,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import TagInput from '@/ui/TagInput'
import EmptyState from '@/ui/EmptyState'
import {
  startAgentRun,
  getAgentRun,
  getAgentRegistry,
  getAgentHealth,
  getAgentRuns,
} from '@/lib/api'
import { errorMessage, titleCase, confidenceColor, formatDate } from '@/lib/utils'

const HEALTH_POLL_MS = 30_000

// Agent status → visual treatment.
const STATUS = {
  pending: { tone: 'neutral', color: 'var(--muted)', icon: Circle, label: 'Pending' },
  running: { tone: 'primary', color: 'var(--primary)', icon: Loader2, label: 'Running', spin: true },
  completed: { tone: 'success', color: 'var(--success)', icon: CheckCircle2, label: 'Completed' },
  skipped: { tone: 'warning', color: 'var(--warning)', icon: MinusCircle, label: 'Skipped' },
  failed: { tone: 'danger', color: 'var(--danger)', icon: XCircle, label: 'Failed' },
}
const st = (s) => STATUS[s] || STATUS.pending

const RUN_STATUS_TONE = { pending: 'neutral', running: 'primary', completed: 'success', failed: 'danger' }

function fmtMs(ms) {
  if (!ms) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

// A single agent node in the animated pipeline.
function AgentNode({ agent, isCurrent }) {
  const cfg = st(agent.status)
  const Icon = cfg.icon
  return (
    <div
      className={`relative flex w-40 shrink-0 flex-col items-center gap-2 rounded-2xl border p-3 text-center transition-all ${
        isCurrent ? 'border-primary shadow-md' : 'border-border'
      }`}
      style={{ backgroundColor: agent.status === 'pending' ? 'transparent' : `${cfg.color}0f` }}
    >
      {isCurrent && <span className="absolute inset-0 animate-pulse rounded-2xl ring-2 ring-primary/40" />}
      <span
        className="grid h-10 w-10 place-items-center rounded-xl"
        style={{ backgroundColor: `${cfg.color}1a`, color: cfg.color }}
      >
        <Icon size={20} className={cfg.spin ? 'animate-spin' : ''} />
      </span>
      <p className="text-xs font-semibold leading-tight text-foreground">{agent.title}</p>
      <div className="flex items-center gap-1.5">
        <Badge tone={cfg.tone}>{cfg.label}</Badge>
      </div>
      <div className="flex items-center gap-2 text-[11px] text-muted">
        <span className="inline-flex items-center gap-0.5"><Clock size={11} /> {fmtMs(agent.duration_ms)}</span>
        {agent.confidence != null && (
          <span className="inline-flex items-center gap-0.5" style={{ color: confidenceColor(agent.confidence * 100) }}>
            <Gauge size={11} /> {Math.round(agent.confidence * 100)}%
          </span>
        )}
      </div>
    </div>
  )
}

// True execution timeline: one row per agent, a bar positioned by its actual
// started_at/finished_at offset from the run start — unlike the flat event
// log below, this visually shows concurrent agents (e.g. Disease ‖ Drug
// Interaction, Explainability ‖ Evidence Verification) as overlapping bars.
function AgentGantt({ run }) {
  const rows = (run?.agents || []).filter((a) => a.started_at)
  if (!run?.started_at || rows.length === 0) return null

  const startMs = new Date(run.started_at).getTime()
  const endMs = run.finished_at ? new Date(run.finished_at).getTime() : Date.now()
  const totalMs = Math.max(1, endMs - startMs)

  return (
    <div className="space-y-2">
      {rows.map((a) => {
        const cfg = st(a.status)
        const s = new Date(a.started_at).getTime()
        const e = a.finished_at ? new Date(a.finished_at).getTime() : endMs
        const left = Math.max(0, ((s - startMs) / totalMs) * 100)
        const width = Math.min(100 - left, Math.max(0.8, ((e - s) / totalMs) * 100))
        return (
          <div key={a.name} className="flex items-center gap-2">
            <span className="w-36 shrink-0 truncate text-xs font-medium text-foreground" title={a.title}>
              {a.title}
            </span>
            <div className="relative h-5 flex-1 overflow-hidden rounded bg-surface-2">
              <div
                className="absolute top-0 h-full rounded transition-all duration-300"
                style={{ left: `${left}%`, width: `${width}%`, backgroundColor: cfg.color }}
                title={`${a.title}: ${cfg.label} (${fmtMs(a.duration_ms)})`}
              />
            </div>
            <span className="w-14 shrink-0 text-right text-[11px] text-muted">{fmtMs(a.duration_ms)}</span>
          </div>
        )
      })}
    </div>
  )
}

// One tile in the Agent Status Dashboard's health grid.
function HealthTile({ health }) {
  const healthy = health.healthy
  const color = !health.enabled ? 'var(--muted)' : healthy ? 'var(--success)' : 'var(--danger)'
  return (
    <div className="rounded-xl border border-border bg-surface p-3" title={health.detail}>
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-xs font-semibold text-foreground">{health.title}</p>
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />
      </div>
      <p className="mt-1 text-[11px] text-muted">
        {!health.enabled ? 'Disabled' : healthy ? 'Healthy' : 'Unavailable'}
      </p>
    </div>
  )
}

const RUN_ROW_TONE = { pending: 'neutral', running: 'primary', completed: 'success', failed: 'danger' }

export default function AgentMonitor() {
  const [registry, setRegistry] = useState(null)
  const [health, setHealth] = useState(null)
  const [recentRuns, setRecentRuns] = useState([])
  const [symptoms, setSymptoms] = useState([])
  const [medicines, setMedicines] = useState([])
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [run, setRun] = useState(null)
  const [running, setRunning] = useState(false)
  const pollRef = useRef(null)
  const healthPollRef = useRef(null)
  const fileRef = useRef(null)

  const refreshRuns = () => getAgentRuns(10).then(setRecentRuns).catch(() => {})
  const refreshHealth = (force = false) => getAgentHealth(force).then(setHealth).catch(() => {})

  useEffect(() => {
    getAgentRegistry().then(setRegistry).catch(() => {})
    refreshHealth()
    refreshRuns()
    healthPollRef.current = setInterval(refreshHealth, HEALTH_POLL_MS)
    return () => {
      clearInterval(pollRef.current)
      clearInterval(healthPollRef.current)
    }
  }, [])

  const poll = (runId) => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const state = await getAgentRun(runId)
        setRun(state)
        if (state.status === 'completed' || state.status === 'failed') {
          clearInterval(pollRef.current)
          setRunning(false)
          refreshRuns()
          refreshHealth()
        }
      } catch {
        clearInterval(pollRef.current)
        setRunning(false)
      }
    }, 1200)
  }

  // Load a past run from the Agent Status Dashboard's recent-runs list.
  const loadRun = async (runId) => {
    clearInterval(pollRef.current)
    setRunning(false)
    try {
      setRun(await getAgentRun(runId))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load that run'))
    }
  }

  const launch = async () => {
    if (!file && symptoms.length === 0 && medicines.length === 0 && !text.trim()) {
      toast.error('Provide a prescription image, symptoms, or medicines.')
      return
    }
    setRunning(true)
    setRun(null)
    try {
      const { run_id } = await startAgentRun({ file, symptoms, medicines, text })
      const first = await getAgentRun(run_id)
      setRun(first)
      poll(run_id)
    } catch (err) {
      toast.error(errorMessage(err, 'Could not start the pipeline'))
      setRunning(false)
    }
  }

  const pickFile = (f) => {
    if (!f) return
    if (!f.type.startsWith('image/')) return toast.error('Please choose an image file')
    setFile(f)
    setPreview(URL.createObjectURL(f))
  }

  // Build the pipeline node list — live run if present, else the static registry.
  const nodes = useMemo(() => {
    if (run?.agents?.length) return run.agents
    if (registry?.agents?.length) {
      return registry.agents.map((a) => ({ name: a.name, title: a.title, status: 'pending', duration_ms: 0 }))
    }
    return []
  }, [run, registry])

  const llmProvider = registry?.llm_provider || 'offline'

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-foreground">
            <Workflow size={22} className="text-primary" /> AI Agent Monitor
          </h1>
          <p className="text-sm text-muted">
            Live view of the multi-agent medical copilot pipeline.
          </p>
        </div>
        <Badge tone="primary"><Cpu size={13} /> LLM: {titleCase(llmProvider)}</Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Input panel */}
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader icon={Play} title="Run the pipeline" subtitle="Upload a prescription and/or enter details" />

            {/* Optional image */}
            {!preview ? (
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="flex w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed border-border p-6 text-center hover:border-primary/50 hover:bg-surface-2"
              >
                <UploadCloud size={22} className="text-primary" />
                <p className="mt-2 text-sm font-medium text-foreground">Add a prescription image (optional)</p>
                <p className="text-xs text-muted">PNG, JPG, WEBP</p>
              </button>
            ) : (
              <div className="relative overflow-hidden rounded-2xl border border-border">
                <img src={preview} alt="preview" className="max-h-40 w-full bg-surface-2 object-contain" />
                <button
                  onClick={() => { setFile(null); setPreview(null) }}
                  className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full bg-black/60 text-white"
                >
                  <X size={14} />
                </button>
              </div>
            )}
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => pickFile(e.target.files?.[0])} />

            <div className="mt-4 space-y-3">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-muted">Symptoms</label>
                <div className="mt-1"><TagInput value={symptoms} onChange={setSymptoms} suggestions={[]} placeholder="e.g. fever, cough" disabled={running} /></div>
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-muted">Medicines</label>
                <div className="mt-1"><TagInput value={medicines} onChange={setMedicines} suggestions={[]} placeholder="e.g. Augmentin 625, Dolo 650" disabled={running} /></div>
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wide text-muted">Notes (optional)</label>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  disabled={running}
                  rows={2}
                  placeholder="Free-text context…"
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
                />
              </div>
            </div>

            <Button className="mt-4 w-full" onClick={launch} loading={running} disabled={running}>
              <Play size={16} /> Run Multi-Agent Pipeline
            </Button>
          </Card>

          {/* Run status */}
          {run && (
            <Card>
              <CardHeader icon={Activity} title="Run status" />
              <div className="flex items-center justify-between">
                <Badge tone={RUN_STATUS_TONE[run.status]}>{titleCase(run.status)}</Badge>
                <span className="text-sm text-muted">{run.completed_agents}/{run.total_agents} agents</span>
              </div>
              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-surface-2">
                <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${Math.round((run.progress || 0) * 100)}%` }} />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-xl bg-surface-2 p-2.5">
                  <p className="text-[11px] uppercase tracking-wide text-muted">Elapsed</p>
                  <p className="font-semibold text-foreground">{fmtMs(run.duration_ms)}</p>
                </div>
                <div className="rounded-xl bg-surface-2 p-2.5">
                  <p className="text-[11px] uppercase tracking-wide text-muted">Confidence</p>
                  <p className="font-semibold" style={{ color: confidenceColor((run.overall_confidence || 0) * 100) }}>
                    {run.overall_confidence != null ? `${Math.round(run.overall_confidence * 100)}%` : '—'}
                  </p>
                </div>
              </div>
              {run.current_agent && (
                <p className="mt-3 flex items-center gap-2 text-sm text-foreground">
                  <Loader2 size={14} className="animate-spin text-primary" />
                  Current: <span className="font-semibold">{titleCase(run.current_agent)}</span>
                </p>
              )}
            </Card>
          )}

          {/* Agent Status Dashboard */}
          <Card>
            <CardHeader
              icon={HeartPulse}
              title="Agent Status Dashboard"
              subtitle={health ? `${health.healthy_agents}/${health.total_agents} agents healthy` : 'Probing agents…'}
              action={
                <button
                  onClick={() => refreshHealth(true)}
                  aria-label="Refresh agent health"
                  title="Refresh agent health"
                  className="grid h-8 w-8 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
                >
                  <RefreshCw size={15} />
                </button>
              }
            />
            {health && (
              <>
                <div className="mb-2 flex items-center gap-2">
                  <Badge tone={health.status === 'ok' ? 'success' : health.status === 'degraded' ? 'warning' : 'danger'}>
                    {titleCase(health.status)}
                  </Badge>
                  <span className="text-xs text-muted">LLM: {titleCase(health.llm_provider)}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {health.agents.map((h) => <HealthTile key={h.name} health={h} />)}
                </div>
              </>
            )}

            {recentRuns.length > 0 && (
              <div className="mt-4 border-t border-border pt-4">
                <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  <HistoryIcon size={13} /> Recent runs
                </p>
                <div className="space-y-1.5">
                  {recentRuns.map((r) => (
                    <button
                      key={r.run_id}
                      onClick={() => loadRun(r.run_id)}
                      className="flex w-full items-center gap-2 rounded-lg bg-surface-2 px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-surface-2/70"
                    >
                      <Badge tone={RUN_ROW_TONE[r.status] || 'neutral'}>{titleCase(r.status)}</Badge>
                      <span className="truncate text-muted">{titleCase(r.task_type)}</span>
                      <span className="ml-auto shrink-0 text-muted">{fmtMs(r.duration_ms)}</span>
                      <span className="shrink-0 text-muted">{formatDate(r.created_at)}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* Pipeline + observability */}
        <div className="space-y-5 lg:col-span-3">
          {/* Animated pipeline */}
          <Card>
            <CardHeader icon={Workflow} title="Agent Pipeline" subtitle="OCR → Medicine → Disease ‖ Interactions → Knowledge → Clinical → Explainability ‖ Evidence Verification → Report → Audit" />
            {nodes.length === 0 ? (
              <EmptyState icon={Workflow} title="Pipeline will appear here" description="Run the pipeline to watch each agent execute in real time." />
            ) : (
              <div className="flex items-stretch gap-1 overflow-x-auto pb-2">
                {nodes.map((a, i) => (
                  <div key={a.name} className="flex items-center gap-1">
                    <AgentNode agent={a} isCurrent={run?.current_agent === a.name} />
                    {i < nodes.length - 1 && (
                      <ChevronRight
                        size={18}
                        className={a.status === 'completed' || a.status === 'skipped' ? 'text-success' : 'text-border'}
                      />
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Execution Timeline — true time-axis view, shows parallel agents as overlapping bars */}
          {run && (
            <Card>
              <CardHeader
                icon={GanttChartSquare}
                title="Execution Timeline"
                subtitle="Each agent's actual start → finish offset — overlapping bars are running in parallel"
              />
              {run.agents?.some((a) => a.started_at) ? (
                <AgentGantt run={run} />
              ) : (
                <p className="text-sm text-muted">Waiting for the first agent to start…</p>
              )}
            </Card>
          )}

          {/* Event log */}
          {run?.timeline?.length > 0 && (
            <Card>
              <CardHeader icon={ListChecks} title="Event Log" subtitle="Milestones as each stage finishes" />
              <ul className="space-y-1.5">
                {run.timeline
                  .filter((t) => ['agent_completed', 'agent_skipped', 'agent_failed', 'workflow_completed'].includes(t.type))
                  .map((t, i) => {
                    const done = t.type === 'agent_completed' || t.type === 'workflow_completed'
                    return (
                      <li key={i} className="flex items-center justify-between gap-2 rounded-lg bg-surface-2 px-3 py-2 text-sm">
                        <span className="flex items-center gap-2 text-foreground">
                          {done ? <CheckCircle2 size={14} className="text-success" /> : t.type === 'agent_skipped' ? <MinusCircle size={14} className="text-warning" /> : <XCircle size={14} className="text-danger" />}
                          {t.message}
                        </span>
                        <span className="shrink-0 text-xs text-muted">{fmtMs(t.elapsed_ms)}</span>
                      </li>
                    )
                  })}
              </ul>
            </Card>
          )}

          {/* Result summary */}
          {run?.status === 'completed' && run?.result && (
            <Card className="border-success/30 bg-success/5">
              <CardHeader icon={CheckCircle2} title="Result summary" />
              <div className="grid gap-2 text-sm sm:grid-cols-2">
                {run.result.medicines?.length > 0 && (
                  <div className="rounded-xl bg-surface-2 p-3">
                    <p className="text-[11px] uppercase tracking-wide text-muted">Medicines</p>
                    <p className="text-foreground">{run.result.medicines.map(titleCase).join(', ')}</p>
                  </div>
                )}
                {run.result.disease?.length > 0 && (
                  <div className="rounded-xl bg-surface-2 p-3">
                    <p className="text-[11px] uppercase tracking-wide text-muted">Top conditions</p>
                    <p className="text-foreground">{run.result.disease.map((d) => d.disease).join(', ')}</p>
                  </div>
                )}
                {run.result.interactions && (
                  <div className="rounded-xl bg-surface-2 p-3">
                    <p className="text-[11px] uppercase tracking-wide text-muted">Interactions</p>
                    <p className="text-foreground">Risk: {run.result.interactions.overall_risk} · {run.result.interactions.count} found</p>
                  </div>
                )}
                {run.result.clinical?.risk_level && (
                  <div className="rounded-xl bg-surface-2 p-3">
                    <p className="text-[11px] uppercase tracking-wide text-muted">Clinical risk</p>
                    <p className="text-foreground">{titleCase(run.result.clinical.risk_level)}</p>
                  </div>
                )}
                {run.result.knowledge_sources?.length > 0 && (
                  <div className="rounded-xl bg-surface-2 p-3 sm:col-span-2">
                    <p className="text-[11px] uppercase tracking-wide text-muted">Knowledge sources</p>
                    <p className="text-foreground">{run.result.knowledge_sources.join(', ')}</p>
                  </div>
                )}
                {run.result.report_id && (
                  <div className="rounded-xl bg-surface-2 p-3 sm:col-span-2">
                    <p className="text-[11px] uppercase tracking-wide text-muted">Report generated</p>
                    <p className="font-mono text-xs text-foreground">{run.result.report_id}</p>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Logs */}
          {run?.logs?.length > 0 && (
            <Card>
              <CardHeader icon={ScrollText} title="Execution logs" />
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-surface-2 p-3 text-xs leading-relaxed text-muted">
                {run.logs.join('\n')}
              </pre>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
