import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Send,
  Plus,
  MessageSquareText,
  Bot,
  User,
  Trash2,
  AlertTriangle,
  Stethoscope,
  ClipboardList,
  ShieldAlert,
  Activity,
} from 'lucide-react'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import ConfidenceBar from '@/ui/ConfidenceBar'
import { cn, titleCase } from '@/lib/utils'
import { predictDisease } from '@/lib/api'
import { savePrediction } from '@/lib/storage'
import {
  detectEmergency,
  detectSymptoms,
  FOLLOWUPS,
  QUESTION_REGISTRY,
  RED_FLAG_SYMPTOMS,
  QUICK_ACTIONS,
  band,
  buildRecommendation,
} from '@/lib/triage'

const CHAT_KEY = 'medisense-chats'
const uid = () => crypto.randomUUID()
const delay = (ms) => new Promise((r) => setTimeout(r, ms))

const GREETING =
  "Hi, I'm your **MediSense triage assistant**. Tell me what's bothering you — " +
  "for example *fever*, *cough*, or *headache* — and I'll ask a few questions to " +
  'understand it better. I share general information only, not a medical diagnosis.'

function newConversation() {
  return {
    id: uid(),
    title: 'New chat',
    messages: [{ id: uid(), role: 'assistant', type: 'text', content: GREETING }],
    tri: { symptoms: [], asked: [], queue: [], assessed: false, emergency: false },
  }
}

function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(CHAT_KEY))
    if (Array.isArray(raw) && raw.length) return raw
  } catch {
    /* ignore */
  }
  return [newConversation()]
}

const norm = (s) => s.toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()

export default function Chat() {
  const [conversations, setConversations] = useState(load)
  const [activeId, setActiveId] = useState(conversations[0].id)
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [streamingId, setStreamingId] = useState(null)
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef(null)

  // Refs mirror state so async triage steps always read the latest value.
  const ref = useRef(conversations)
  const activeRef = useRef(activeId)
  const setConvs = (next) => {
    ref.current = next
    setConversations(next)
  }
  useEffect(() => {
    activeRef.current = activeId
  }, [activeId])

  // Persist (Requirement #8)
  useEffect(() => {
    try {
      localStorage.setItem(CHAT_KEY, JSON.stringify(conversations))
    } catch {
      /* quota */
    }
  }, [conversations])

  const active = conversations.find((c) => c.id === activeId) ?? conversations[0]

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [active?.messages, typing])

  // ---------- state helpers (ref-backed) ----------
  const getActive = () =>
    ref.current.find((c) => c.id === activeRef.current) ?? ref.current[0]

  const updateActive = (updater) =>
    setConvs(ref.current.map((c) => (c.id === activeRef.current ? updater(c) : c)))

  const pushMsg = (msg) =>
    updateActive((c) => {
      const isFirstUser = msg.role === 'user' && !c.messages.some((m) => m.role === 'user')
      return {
        ...c,
        title: isFirstUser ? msg.content.slice(0, 36) : c.title,
        messages: [...c.messages, msg],
      }
    })

  const addSymptom = (sym) =>
    updateActive((c) =>
      c.tri.symptoms.some((s) => norm(s) === norm(sym))
        ? c
        : { ...c, tri: { ...c.tri, symptoms: [...c.tri.symptoms, sym] } },
    )

  // ---------- bot turns ----------
  async function botStream(type, content, extra = {}) {
    setTyping(true)
    await delay(450)
    setTyping(false)
    const msg = { id: uid(), role: 'assistant', type, content, ...extra }
    pushMsg(msg)
    setStreamingId(msg.id)
  }

  async function botEmergency(emg) {
    setTyping(true)
    await delay(350)
    setTyping(false)
    pushMsg({ id: uid(), role: 'assistant', type: 'emergency', content: emg.message, title: emg.title })
  }

  async function botContinue() {
    const c = getActive()
    if (c.tri.queue.length) {
      const qid = c.tri.queue[0]
      const q = QUESTION_REGISTRY[qid]
      updateActive((cc) => ({
        ...cc,
        tri: { ...cc.tri, queue: cc.tri.queue.slice(1), asked: [...cc.tri.asked, qid] },
      }))
      await botStream('question', q.q, { qid: q.id, options: q.options })
    } else if (!c.tri.symptoms.length) {
      await botStream('text', 'Could you tell me your main symptom? For example: **fever**, **cough**, **headache**, or **stomach pain**.')
    } else if (!c.tri.assessed) {
      await botAssess()
    }
  }

  async function botAssess() {
    setTyping(true)
    await delay(700)
    const c = getActive()
    const symptoms = c.tri.symptoms
    let predictions = []
    let apiOk = true
    try {
      const data = await predictDisease(symptoms, 3)
      predictions = data.predictions || []
    } catch {
      apiOk = false
    }
    setTyping(false)

    const redFlags = symptoms.filter((s) => RED_FLAG_SYMPTOMS.has(norm(s)))
    const topConfidence = predictions[0]?.confidence ?? 0
    const recommendation = buildRecommendation({
      emergency: c.tri.emergency,
      redFlags,
      topConfidence,
    })

    pushMsg({
      id: uid(),
      role: 'assistant',
      type: 'assessment',
      data: { reported: symptoms, predictions: predictions.slice(0, 3), redFlags, recommendation, apiOk },
    })
    updateActive((cc) => ({ ...cc, tri: { ...cc.tri, assessed: true } }))

    if (predictions.length) {
      savePrediction({
        symptoms,
        topDisease: predictions[0].disease,
        confidence: predictions[0].confidence,
        level: band(predictions[0].confidence).label.toLowerCase(),
      })
    }
  }

  // Detect symptoms in text, record them, and queue their follow-ups.
  function ingest(text) {
    const found = detectSymptoms(text)
    const c = getActive()
    const queued = new Set([...c.tri.asked, ...c.tri.queue])
    const newQ = []
    for (const { symptom, label } of found) {
      addSymptom(symptom)
      const qs = FOLLOWUPS[label]
      if (qs) for (const q of qs) if (!queued.has(q.id)) { queued.add(q.id); newQ.push(q.id) }
    }
    if (newQ.length) {
      updateActive((cc) => ({
        ...cc,
        tri: { ...cc.tri, queue: [...cc.tri.queue, ...newQ], assessed: false },
      }))
    }
    return found
  }

  // ---------- user actions ----------
  async function send(text = input) {
    const content = text.trim()
    if (!content || busy) return
    setInput('')
    setBusy(true)
    try {
      pushMsg({ id: uid(), role: 'user', type: 'text', content })

      const emg = detectEmergency(content)
      if (emg && !getActive().tri.emergency) {
        updateActive((c) => ({ ...c, tri: { ...c.tri, emergency: true } }))
        await botEmergency(emg)
      }
      ingest(content)
      await botContinue()
    } finally {
      setBusy(false)
    }
  }

  async function answer(option) {
    if (busy) return
    setBusy(true)
    try {
      pushMsg({ id: uid(), role: 'user', type: 'text', content: option.label })
      if (option.add) addSymptom(option.add)
      await botContinue()
    } finally {
      setBusy(false)
    }
  }

  async function assessNow() {
    if (busy) return
    setBusy(true)
    try {
      updateActive((c) => ({ ...c, tri: { ...c.tri, queue: [] } }))
      await botAssess()
    } finally {
      setBusy(false)
    }
  }

  const addChat = () => {
    const c = newConversation()
    setConvs([c, ...ref.current])
    setActiveId(c.id)
  }

  const deleteChat = (id) => {
    const next = ref.current.filter((c) => c.id !== id)
    const safe = next.length ? next : [newConversation()]
    setConvs(safe)
    if (id === activeId) setActiveId(safe[0].id)
  }

  // The latest question message is the only one that should show clickable chips.
  const lastQuestionId = useMemo(() => {
    const qs = active.messages.filter((m) => m.type === 'question')
    return qs.length ? qs[qs.length - 1].id : null
  }, [active.messages])

  const showQuickActions = active.tri.symptoms.length === 0 && !busy
  const canAssess = active.tri.symptoms.length > 0 && !active.tri.assessed

  return (
    <div className="grid h-[calc(100vh-8.5rem)] grid-cols-1 gap-4 lg:grid-cols-4">
      {/* History sidebar */}
      <aside className="hidden flex-col rounded-2xl border border-border bg-surface p-3 lg:flex">
        <Button onClick={addChat} className="w-full">
          <Plus size={16} /> New chat
        </Button>
        <div className="mt-3 flex-1 space-y-1 overflow-auto">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={cn(
                'group flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm transition-colors',
                c.id === activeId ? 'bg-primary-soft text-primary' : 'text-muted hover:bg-surface-2',
              )}
            >
              <button onClick={() => setActiveId(c.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                <MessageSquareText size={15} className="shrink-0" />
                <span className="truncate">{c.title}</span>
              </button>
              <button
                onClick={() => deleteChat(c.id)}
                aria-label="Delete chat"
                className="opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Chat window */}
      <div className="flex flex-col overflow-hidden rounded-2xl border border-border bg-surface lg:col-span-3">
        <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary to-accent text-white">
            <Stethoscope size={18} />
          </span>
          <div>
            <p className="font-semibold text-foreground">Triage Assistant</p>
            <p className="text-xs text-success">● Online · informational only</p>
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-5 overflow-auto p-5">
          {active.messages.map((m) => (
            <Message
              key={m.id}
              msg={m}
              streaming={streamingId === m.id}
              onStreamDone={() => setStreamingId((id) => (id === m.id ? null : id))}
              showChips={m.id === lastQuestionId && !active.tri.assessed && !busy && streamingId !== m.id}
              onAnswer={answer}
            />
          ))}
          {typing && <TypingBubble />}

          {/* Quick actions (Requirement #11) */}
          {showQuickActions && (
            <div className="mt-2 flex flex-wrap gap-2">
              {QUICK_ACTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-2 text-sm text-foreground transition-colors hover:border-primary/50 hover:bg-surface-2"
                >
                  <Plus size={13} className="text-primary" /> {q}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="border-t border-border p-3">
          {canAssess && (
            <div className="mb-2 flex justify-center">
              <Button size="sm" variant="secondary" onClick={assessNow} disabled={busy}>
                <ClipboardList size={15} /> Get assessment now
              </Button>
            </div>
          )}
          <div className="flex items-end gap-2 rounded-2xl border border-border bg-background p-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
              rows={1}
              placeholder="Describe your symptoms…"
              className="max-h-32 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-foreground outline-none placeholder:text-muted"
            />
            <Button size="icon" onClick={() => send()} disabled={!input.trim() || busy}>
              <Send size={16} />
            </Button>
          </div>
          <p className="mt-2 text-center text-[11px] text-muted">
            Triage assistant — general information only. Not a diagnosis. In an emergency, call your local emergency number.
          </p>
        </div>
      </div>
    </div>
  )
}

// ============================================================
//  Message renderer
// ============================================================
function Message({ msg, streaming, onStreamDone, showChips, onAnswer }) {
  if (msg.type === 'emergency') return <EmergencyBubble title={msg.title} content={msg.content} />
  if (msg.type === 'assessment') return <Assessment data={msg.data} />

  const isUser = msg.role === 'user'
  return (
    <div className={cn('flex animate-fade-up gap-3', isUser && 'flex-row-reverse')}>
      <span
        className={cn(
          'grid h-8 w-8 shrink-0 place-items-center rounded-lg',
          isUser ? 'bg-surface-2 text-foreground' : 'bg-gradient-to-br from-primary to-accent text-white',
        )}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </span>
      <div className="max-w-[82%] space-y-2">
        <div
          className={cn(
            'rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
            isUser ? 'rounded-tr-sm bg-primary text-primary-foreground' : 'rounded-tl-sm bg-surface-2 text-foreground',
          )}
        >
          {streaming ? (
            <TypingText text={msg.content} onDone={onStreamDone} />
          ) : (
            <span dangerouslySetInnerHTML={{ __html: renderMd(msg.content) }} />
          )}
        </div>

        {/* Follow-up quick replies */}
        {msg.type === 'question' && showChips && msg.options?.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {msg.options.map((opt) => (
              <button
                key={opt.label}
                onClick={() => onAnswer(opt)}
                className="rounded-full border border-primary/30 bg-surface px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function EmergencyBubble({ title, content }) {
  return (
    <div className="animate-fade-up rounded-2xl border border-danger/40 bg-danger/10 p-4">
      <div className="flex items-start gap-3">
        <ShieldAlert size={22} className="mt-0.5 shrink-0 text-danger" />
        <div>
          <p className="font-semibold text-danger">⚠ {title}</p>
          <p className="mt-1 text-sm text-foreground">{content}</p>
        </div>
      </div>
    </div>
  )
}

const REC_TONE = {
  danger: 'border-danger/40 bg-danger/10 text-danger',
  warning: 'border-warning/40 bg-warning/10 text-warning',
  primary: 'border-primary/30 bg-primary-soft text-primary',
}

function Assessment({ data }) {
  const { reported, predictions, redFlags, recommendation, apiOk } = data
  return (
    <div className="animate-fade-up space-y-4 rounded-2xl border border-border bg-background p-5">
      <div className="flex items-center gap-2">
        <ClipboardList size={18} className="text-primary" />
        <h3 className="font-semibold text-foreground">Triage Summary</h3>
      </div>

      {/* Reported symptoms */}
      <div>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Reported symptoms</p>
        <div className="flex flex-wrap gap-1.5">
          {reported.map((s) => (
            <Badge key={s} tone="neutral">{titleCase(s)}</Badge>
          ))}
        </div>
      </div>

      {/* Red flags */}
      {redFlags.length > 0 && (
        <div className="flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-danger" />
          <span className="text-foreground">
            <span className="font-semibold text-danger">Red-flag symptoms:</span>{' '}
            {redFlags.map(titleCase).join(', ')} — these can be serious and warrant prompt medical review.
          </span>
        </div>
      )}

      {/* Possible conditions (Requirement #4 + #10) */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Possible conditions</p>
        {!apiOk ? (
          <p className="text-sm text-muted">Couldn’t reach the prediction service. Please try again.</p>
        ) : predictions.length === 0 ? (
          <p className="text-sm text-muted">Not enough specific symptoms to suggest a likely condition.</p>
        ) : (
          <div className="space-y-3">
            {predictions.map((p) => {
              const b = band(p.confidence)
              return (
                <div key={p.disease} className="rounded-xl border border-border bg-surface p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Possible condition</p>
                      <p className="font-semibold text-foreground">{p.disease}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className="text-sm font-bold text-foreground">{Number(p.confidence).toFixed(1)}%</span>
                      <Badge tone={b.tone}>{b.label}</Badge>
                    </div>
                  </div>
                  <div className="mt-2">
                    <ConfidenceBar value={Number(p.confidence)} showLabel={false} />
                  </div>
                  {p.explanation && (
                    <p className="mt-2 text-xs text-muted">
                      <span className="font-medium text-foreground">Why this may match: </span>
                      {p.explanation}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Recommendation */}
      <div className={cn('rounded-xl border p-3 text-sm', REC_TONE[recommendation.tone])}>
        <p className="font-semibold">Recommendation</p>
        <p className="mt-0.5 text-foreground">{recommendation.text}</p>
      </div>

      <p className="text-[11px] text-muted">
        This is a possible-condition estimate from an educational model — not a diagnosis. Please confirm with a licensed clinician.
      </p>
    </div>
  )
}

function TypingBubble() {
  return (
    <div className="flex gap-3">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-primary to-accent text-white">
        <Bot size={16} />
      </span>
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm bg-surface-2 px-4 py-3.5">
        {[0, 200, 400].map((d) => (
          <span key={d} className="typing-dot h-2 w-2 rounded-full bg-muted" style={{ animationDelay: `${d}ms` }} />
        ))}
      </div>
    </div>
  )
}

// ---------- streaming text (Requirement #7) ----------
function TypingText({ text, onDone, speed = 12 }) {
  const [n, setN] = useState(0)
  const doneRef = useRef(onDone)
  doneRef.current = onDone
  useEffect(() => {
    setN(0)
    let i = 0
    const id = setInterval(() => {
      i += 1
      setN(i)
      if (i >= text.length) {
        clearInterval(id)
        doneRef.current?.()
      }
    }, speed)
    return () => clearInterval(id)
  }, [text, speed])
  return <span dangerouslySetInnerHTML={{ __html: renderMd(text.slice(0, n)) }} />
}

// Minimal, safe markdown: escape, then **bold** and *italic*.
function renderMd(text) {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
}
