import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Bot,
  User,
  Pill,
  FileText,
  Clock,
  Workflow,
  GitCompareArrows,
  Stethoscope,
  Gauge,
  ClipboardCheck,
  Library,
  Sparkles,
  Upload,
  Send,
  MessageSquareText,
  BookOpen,
  Activity,
  ChevronRight,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import TagInput from '@/ui/TagInput'
import ConfidenceBar from '@/ui/ConfidenceBar'
import ReasoningPipeline from '@/ui/ReasoningPipeline'
import {
  copilotAnalyze,
  copilotChat,
  getCopilotContext,
  getCopilotHistory,
  getCopilotPipeline,
  getSymptoms,
} from '@/lib/api'
import { errorMessage, titleCase, formatDate } from '@/lib/utils'

const SESSION_KEY = 'copilot_session_id'
const RISK_TONE = { critical: 'danger', high: 'danger', moderate: 'warning', low: 'primary' }

const FALLBACK_PIPELINE = [
  ['receive', 'Receive Prescription'], ['ocr', 'Run OCR'],
  ['extract_medicines', 'Extract Medicines'], ['drug_interactions', 'Check Drug Interactions'],
  ['disease_prediction', 'Predict Disease'], ['evidence', 'Retrieve Medical Evidence'],
  ['clinical_decision', 'Generate Clinical Decision'], ['summary', 'Generate AI Summary'],
  ['treatment', 'Generate Treatment Suggestions'], ['follow_up', 'Generate Follow-up Suggestions'],
  ['report', 'Generate Final Medical Report'],
].map(([key, name], i) => ({ order: i + 1, key, name }))

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

// ---- Small labelled panel section ----
function Panel({ icon: Icon, title, children, action, className = '' }) {
  return (
    <Card className={className}>
      <CardHeader icon={Icon} title={title} action={action} />
      {children}
    </Card>
  )
}

// ---- Left: AI Activity Timeline ----
function ActivityTimeline({ events }) {
  if (!events?.length) {
    return <p className="text-sm text-muted">No activity yet. Run an analysis to begin.</p>
  }
  return (
    <ol className="relative space-y-0">
      {events.map((e, i) => {
        const failed = e.status === 'failed'
        return (
          <li key={i} className="reasoning-node-in flex gap-3" style={{ animationDelay: `${i * 40}ms` }}>
            <div className="flex flex-col items-center">
              <span
                className={`grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 ${
                  failed ? 'border-danger bg-danger/10 text-danger' : 'border-success bg-success/10 text-success'
                }`}
              >
                {failed ? <AlertTriangle size={13} /> : <CheckCircle2 size={13} />}
              </span>
              {i < events.length - 1 && <span className="my-0.5 w-0.5 flex-1 rounded-full bg-border" />}
            </div>
            <div className="min-w-0 flex-1 pb-3">
              <p className="text-[11px] tabular-nums text-muted">{fmtTime(e.at)}</p>
              <p className="text-sm font-medium text-foreground">{e.label}</p>
              {e.detail && <p className="truncate text-xs text-muted">{e.detail}</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

// ---- Center tabs ----
const TABS = [
  { key: 'conversation', label: 'Conversation', icon: MessageSquareText },
  { key: 'reasoning', label: 'AI Reasoning', icon: Workflow },
  { key: 'evidence', label: 'Evidence', icon: BookOpen },
  { key: 'analysis', label: 'Current Analysis', icon: Activity },
]

export default function CopilotWorkspace() {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(SESSION_KEY) || null)
  const [file, setFile] = useState(null)
  const [medicines, setMedicines] = useState([])
  const [symptoms, setSymptoms] = useState([])
  const [symptomOptions, setSymptomOptions] = useState([])
  const [loading, setLoading] = useState(false)
  const [analysis, setAnalysis] = useState(null)
  const [context, setContext] = useState(null)
  const [messages, setMessages] = useState([])
  const [pipeline, setPipeline] = useState(FALLBACK_PIPELINE)
  const [tab, setTab] = useState('conversation')
  const [chatInput, setChatInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const fileRef = useRef(null)
  const chatEndRef = useRef(null)

  const hydrate = async (sid) => {
    try {
      // GET /copilot/context (+ /copilot/history) rehydrate the remembered
      // patient session so a page reload keeps the same patient.
      const [ctx] = await Promise.all([getCopilotContext(sid), getCopilotHistory(sid)])
      setContext(ctx.context)
      setMessages(ctx.messages || [])
      if (ctx.last_analysis) setAnalysis(ctx.last_analysis)
    } catch {
      // Session may have expired server-side — start fresh silently.
      localStorage.removeItem(SESSION_KEY)
      setSessionId(null)
    }
  }

  useEffect(() => {
    getSymptoms().then(setSymptomOptions).catch(() => setSymptomOptions([]))
    getCopilotPipeline().then((s) => s.length && setPipeline(s)).catch(() => {})
    // hydrate is async (awaits the network before any setState) — the rule is a
    // false positive here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (sessionId) hydrate(sessionId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const run = async () => {
    if (!file && !medicines.length && !symptoms.length) {
      toast.error('Upload a prescription or add medicines / symptoms first.')
      return
    }
    setLoading(true)
    setTab('reasoning')
    try {
      const data = await copilotAnalyze({
        file,
        sessionId,
        medicines,
        symptoms,
        includeRag: true,
        useCache: true,
      })
      setAnalysis(data)
      setSessionId(data.session_id)
      localStorage.setItem(SESSION_KEY, data.session_id)
      await hydrate(data.session_id)
      setTab('analysis')
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
      toast.success('Analysis complete — patient context updated.')
    } catch (err) {
      toast.error(errorMessage(err, 'Copilot analysis failed. Is the backend running?'))
    } finally {
      setLoading(false)
    }
  }

  const sendChat = async () => {
    const msg = chatInput.trim()
    if (!msg) return
    if (!sessionId) {
      toast.error('Run an analysis first so the Copilot has patient context.')
      return
    }
    setChatInput('')
    setMessages((m) => [...m, { role: 'user', content: msg, at: new Date().toISOString() }])
    setChatBusy(true)
    try {
      const res = await copilotChat(sessionId, msg)
      setMessages((m) => [...m, { role: 'assistant', content: res.reply, references: res.references, at: res.at }])
    } catch (err) {
      toast.error(errorMessage(err, 'Chat failed.'))
    } finally {
      setChatBusy(false)
    }
  }

  const resetSession = () => {
    localStorage.removeItem(SESSION_KEY)
    setSessionId(null); setContext(null); setMessages([]); setAnalysis(null)
    setMedicines([]); setSymptoms([]); setFile(null)
    toast.success('Started a new patient session.')
  }

  const interactions = analysis?.drug_interactions?.interactions || []
  const timeline = context?.timeline || analysis?.activity || []

  return (
    <div className="grid gap-4 xl:grid-cols-12">
      {/* ============ LEFT PANEL ============ */}
      <aside className="space-y-4 xl:col-span-3">
        <Panel icon={User} title="Patient Context" action={
          <Button size="sm" variant="ghost" onClick={resetSession} aria-label="New session">
            <RotateCcw size={14} /> New
          </Button>
        }>
          {context ? (
            <div className="space-y-1.5 text-sm">
              <Row label="Name" value={context.patient_name || '—'} />
              <Row label="Age" value={context.age ?? '—'} />
              <Row label="Gender" value={context.gender ? titleCase(context.gender) : '—'} />
              <Row label="Analyses" value={context.analysis_count} />
              {context.known_conditions?.length > 0 && (
                <div className="pt-1">
                  <p className="text-[11px] uppercase tracking-wide text-muted">Conditions</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {context.known_conditions.map((c) => <Badge key={c} tone="primary">{titleCase(c)}</Badge>)}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted">No patient yet. Upload a prescription to begin a session.</p>
          )}
        </Panel>

        <Panel icon={Pill} title="Current Medicines">
          {context?.current_medicines?.length ? (
            <div className="flex flex-wrap gap-1.5">
              {context.current_medicines.map((m) => <Badge key={m} tone="neutral">{titleCase(m)}</Badge>)}
            </div>
          ) : <p className="text-sm text-muted">None recorded yet.</p>}
        </Panel>

        <Panel icon={FileText} title="Previous Reports">
          {context?.previous_reports?.length ? (
            <div className="space-y-2">
              {context.previous_reports.slice(0, 8).map((r) => (
                <div key={r.analysis_id} className="flex items-center gap-2 rounded-xl border border-border bg-surface p-2.5">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-surface-2 text-primary">
                    <FileText size={14} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">
                      {r.title ? titleCase(r.title) : 'Analysis'}
                    </p>
                    <p className="truncate text-[11px] text-muted">{formatDate(r.created_at)}</p>
                  </div>
                  <Badge tone={RISK_TONE[r.risk_level] || 'primary'}>{titleCase(r.risk_level)}</Badge>
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-muted">No previous reports in this session.</p>}
        </Panel>

        <Panel icon={Clock} title="AI Activity Timeline">
          <ActivityTimeline events={timeline} />
        </Panel>
      </aside>

      {/* ============ CENTER PANEL ============ */}
      <main className="space-y-4 xl:col-span-6">
        {/* Input / upload bar */}
        <Card>
          <CardHeader icon={Sparkles} title="AI Medical Copilot" subtitle="Upload a prescription or enter details — the Copilot runs the full pipeline" />
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <TagInput value={medicines} onChange={setMedicines} placeholder="Medicines (optional)…" />
              <TagInput value={symptoms} onChange={setSymptoms} suggestions={symptomOptions} placeholder="Symptoms (optional)…" />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
              />
              <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
                <Upload size={15} /> {file ? 'Change image' : 'Upload prescription'}
              </Button>
              {file && <span className="truncate text-xs text-muted">{file.name}</span>}
              <Button className="ml-auto" onClick={run} loading={loading}>
                <Workflow size={16} /> Run Copilot
              </Button>
            </div>
          </div>
        </Card>

        {/* Tabs */}
        <Card>
          <div className="mb-4 flex flex-wrap gap-1 border-b border-border">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                  tab === t.key ? 'border-primary text-primary' : 'border-transparent text-muted hover:text-foreground'
                }`}
              >
                <t.icon size={15} /> {t.label}
              </button>
            ))}
          </div>

          {/* Conversation */}
          {tab === 'conversation' && (
            <div className="flex h-[28rem] flex-col">
              <div className="flex-1 space-y-3 overflow-y-auto pr-1">
                {messages.length === 0 && (
                  <p className="text-sm text-muted">
                    Ask the Copilot anything about the current patient. It answers grounded in the session context.
                  </p>
                )}
                {messages.map((m, i) => <ChatBubble key={i} msg={m} />)}
                {chatBusy && <ChatBubble msg={{ role: 'assistant', content: '…', at: '' }} />}
                <div ref={chatEndRef} />
              </div>
              <div className="mt-3 flex items-center gap-2">
                <input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendChat()}
                  placeholder="Ask about this patient…"
                  className="h-11 flex-1 rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary"
                />
                <Button onClick={sendChat} loading={chatBusy} aria-label="Send">
                  <Send size={16} />
                </Button>
              </div>
            </div>
          )}

          {/* AI Reasoning */}
          {tab === 'reasoning' && (
            loading && !analysis ? (
              <RunningPipeline steps={pipeline} />
            ) : analysis?.reasoning?.length ? (
              <ReasoningPipeline steps={analysis.reasoning} compact />
            ) : <EmptyPanel text="Run the Copilot to see the step-by-step reasoning." />
          )}

          {/* Evidence */}
          {tab === 'evidence' && (
            analysis?.evidence?.length ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {analysis.evidence.map((e) => (
                  <div key={e.id} className="rounded-xl border border-border bg-surface p-3">
                    <div className="flex items-start justify-between gap-2">
                      <h4 className="text-sm font-semibold text-foreground">{e.title}</h4>
                      {e.relevance > 0 && <Badge tone="primary">{Math.round(e.relevance * 100)}%</Badge>}
                    </div>
                    {e.source && <p className="mt-0.5 text-[11px] text-muted">{e.source}</p>}
                    {e.snippet && <p className="mt-1.5 text-xs leading-relaxed text-muted">{e.snippet}</p>}
                  </div>
                ))}
              </div>
            ) : <EmptyPanel text="No knowledge-base evidence retrieved for the latest analysis." />
          )}

          {/* Current Analysis */}
          {tab === 'analysis' && (
            analysis ? <CurrentAnalysis analysis={analysis} /> : <EmptyPanel text="Run the Copilot to see the current analysis." />
          )}
        </Card>
      </main>

      {/* ============ RIGHT PANEL ============ */}
      <aside className="space-y-4 xl:col-span-3">
        <Panel icon={Gauge} title="Confidence">
          {analysis ? (
            <>
              <div className="mb-2 text-center">
                <span className="text-3xl font-bold text-foreground">{Math.round(analysis.confidence)}<span className="text-lg">%</span></span>
                <div className="mt-1"><Badge tone={RISK_TONE[analysis.risk_level] || 'primary'}>Risk: {titleCase(analysis.risk_level)}</Badge></div>
              </div>
              <ConfidenceBar value={analysis.confidence} showLabel={false} />
            </>
          ) : <p className="text-sm text-muted">—</p>}
        </Panel>

        <Panel icon={GitCompareArrows} title="Drug Interactions">
          {interactions.length ? (
            <div className="space-y-2">
              {interactions.map((it, i) => (
                <div key={i} className="rounded-xl border border-border bg-surface p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-foreground">
                      {(it.pair || it.medicines || []).map(titleCase).join(' + ')}
                    </span>
                    <Badge tone={RISK_TONE[(it.severity || '').toLowerCase()] || 'neutral'}>{titleCase(it.severity || 'note')}</Badge>
                  </div>
                  {(it.description || it.effect) && <p className="mt-1 text-xs text-muted">{it.description || it.effect}</p>}
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-muted">No interactions found{analysis ? '.' : ' yet.'}</p>}
        </Panel>

        <Panel icon={Stethoscope} title="Disease Prediction">
          {analysis?.disease_prediction?.length ? (
            <div className="space-y-2">
              {analysis.disease_prediction.slice(0, 5).map((d) => (
                <div key={d.disease}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-foreground">{titleCase(d.disease)}</span>
                    <span className="tabular-nums text-muted">{Math.round(d.confidence)}%</span>
                  </div>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                    <div className="meter-fill h-full rounded-full bg-primary/70" style={{ width: `${Math.min(100, d.confidence)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-muted">No prediction{analysis ? '' : ' yet'}.</p>}
        </Panel>

        <Panel icon={ClipboardCheck} title="Recommendations">
          {analysis?.recommendations?.length ? (
            <ul className="space-y-2">
              {analysis.recommendations.slice(0, 8).map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <ChevronRight size={14} className="mt-0.5 shrink-0 text-primary" />
                  <div>
                    <span className="font-medium text-foreground">{r.title}</span>
                    {r.detail && <p className="text-xs text-muted">{r.detail}</p>}
                  </div>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No recommendations{analysis ? '' : ' yet'}.</p>}
        </Panel>

        <Panel icon={Library} title="Medical References">
          {analysis?.references?.length ? (
            <ul className="space-y-1.5">
              {analysis.references.map((ref, i) => (
                <li key={i} className="text-sm">
                  <span className="text-xs tabular-nums text-muted">[{i + 1}] </span>
                  <span className="font-medium text-foreground">{ref.label}</span>
                  {ref.source && <span className="text-xs text-muted"> — {ref.source}</span>}
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No references{analysis ? '' : ' yet'}.</p>}
        </Panel>
      </aside>
    </div>
  )
}

// ---- Live animated pipeline shown while the workflow runs ----
function RunningPipeline({ steps }) {
  const [active, setActive] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setActive((i) => (i + 1) % steps.length), 650)
    return () => clearInterval(id)
  }, [steps.length])
  const decorated = steps.map((s, i) => ({
    ...s,
    status: i < active ? 'complete' : i === active ? 'running' : 'pending',
    title: i === active ? 'Working…' : '',
  }))
  return <ReasoningPipeline steps={decorated} compact />
}

// ---- helpers / small components ----
function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  )
}

function EmptyPanel({ text }) {
  return (
    <div className="flex items-center justify-center py-10 text-center">
      <p className="max-w-sm text-sm text-muted">{text}</p>
    </div>
  )
}

function ChatBubble({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${isUser ? 'bg-primary text-primary-foreground' : 'bg-surface-2 text-primary'}`}>
        {isUser ? <User size={15} /> : <Bot size={15} />}
      </span>
      <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${isUser ? 'bg-primary text-primary-foreground' : 'bg-surface-2 text-foreground'}`}>
        <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
        {msg.references?.length > 0 && (
          <p className="mt-1 text-[11px] opacity-80">Refs: {msg.references.join(', ')}</p>
        )}
      </div>
    </div>
  )
}

function CurrentAnalysis({ analysis }) {
  return (
    <div className="space-y-4">
      {analysis.summary && (
        <div className="rounded-xl bg-primary-soft/40 p-3">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-primary"><Sparkles size={14} /> AI Summary</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-foreground/90">{analysis.summary}</p>
        </div>
      )}
      {analysis.treatment_suggestions?.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-semibold text-foreground">Treatment Suggestions</p>
          <div className="space-y-2">
            {analysis.treatment_suggestions.map((t, i) => (
              <div key={i} className="rounded-xl border border-border bg-surface p-3">
                <p className="text-sm font-medium text-foreground">{t.suggestion}</p>
                {t.rationale && <p className="text-xs text-muted">Why: {t.rationale}</p>}
                {t.caution && <p className="mt-0.5 text-xs text-warning">Caution: {t.caution}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
      {analysis.follow_up_suggestions?.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-semibold text-foreground">Follow-up Suggestions</p>
          <div className="space-y-2">
            {analysis.follow_up_suggestions.map((f, i) => (
              <div key={i} className="flex items-start gap-2.5 rounded-xl border border-border bg-surface p-2.5">
                <Clock size={15} className="mt-0.5 shrink-0 text-primary" />
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{f.action}</span>
                    {f.timeframe && <Badge tone="primary">{f.timeframe}</Badge>}
                  </div>
                  {f.reason && <p className="text-xs text-muted">{f.reason}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {analysis.report_id && (
        <p className="rounded-xl border border-dashed border-border bg-surface/50 p-2.5 text-xs text-muted">
          A durable medical report was generated (id {analysis.report_id.slice(0, 8)}…) and is available on the Medical Reports page.
        </p>
      )}
      <p className="rounded-xl border border-dashed border-border bg-surface/50 p-3 text-xs leading-relaxed text-muted">
        {analysis.disclaimer}
      </p>
    </div>
  )
}
