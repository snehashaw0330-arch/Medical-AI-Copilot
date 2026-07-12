import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Brain, MessageSquareText, ScanLine, Pill, Stethoscope, ClipboardList,
  Sparkles, Trash2, User, ShieldAlert,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import { CardSkeleton } from '@/ui/Skeleton'
import { listPatientContexts, getPatientContext, deletePatientContext } from '@/lib/api'
import { cn, errorMessage, formatDate } from '@/lib/utils'

// Dotted vertical timeline, matching the pattern used on the Digital Twin page.
function EventTimeline({ events, dotColor = 'var(--primary)', emptyText = 'Nothing on record yet.' }) {
  if (!events?.length) {
    return <p className="text-sm text-muted">{emptyText}</p>
  }
  return (
    <ol className="relative space-y-4 border-l border-border pl-5">
      {events.map((e) => (
        <li key={e.id} className="relative">
          <span
            className="absolute -left-[27px] top-1 grid h-4 w-4 place-items-center rounded-full border-2 border-surface"
            style={{ backgroundColor: dotColor }}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-foreground">{e.title || e.event_type}</p>
            <span className="text-xs text-muted">{formatDate(e.created_at)}</span>
          </div>
          {e.text && <p className="text-xs text-muted">{e.text}</p>}
        </li>
      ))}
    </ol>
  )
}

function ConversationThread({ messages }) {
  if (!messages?.length) {
    return <p className="text-sm text-muted">No conversation recorded yet. Chat in the Copilot Workspace to build history.</p>
  }
  return (
    <div className="space-y-3">
      {messages.map((m) => (
        <div key={m.id} className={cn('flex', m.role === 'assistant' ? 'justify-start' : 'justify-end')}>
          <div
            className={cn(
              'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm',
              m.role === 'assistant'
                ? 'bg-surface-2 text-foreground'
                : 'bg-primary text-primary-foreground'
            )}
          >
            <p>{m.text}</p>
            <p className={cn('mt-1 text-[10px]', m.role === 'assistant' ? 'text-muted' : 'text-primary-foreground/70')}>
              {formatDate(m.created_at)}
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function PatientContext() {
  const [patients, setPatients] = useState([])
  const [patientId, setPatientId] = useState('')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const load = async (id) => {
    if (!id) return
    setPatientId(id)
    setLoading(true)
    try {
      setDetail(await getPatientContext(id))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load patient context'))
    } finally {
      setLoading(false)
    }
  }

  const loadPatients = () => {
    listPatientContexts()
      .then((res) => {
        const items = res.items || []
        setPatients(items)
        if (items.length) load(items[0].patient_id)
        else setDetail(null)
      })
      .catch(() => toast.error('Could not load patient contexts. Is the API running?'))
  }

  useEffect(() => {
    loadPatients()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleDelete = async () => {
    if (!patientId) return
    if (!window.confirm(`Forget everything remembered about "${detail?.profile?.patient_name}"? This cannot be undone.`)) {
      return
    }
    setDeleting(true)
    try {
      await deletePatientContext(patientId)
      toast.success('Patient context deleted')
      setPatientId('')
      setDetail(null)
      loadPatients()
    } catch (err) {
      toast.error(errorMessage(err, 'Delete failed'))
    } finally {
      setDeleting(false)
    }
  }

  const profile = detail?.profile

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-foreground">
            <Brain size={22} className="text-primary" /> Patient Context
          </h1>
          <p className="text-sm text-muted">Durable, cross-session memory of every patient interaction.</p>
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
                {p.patient_name} ({p.event_count})
              </option>
            ))}
          </select>
          <Button variant="danger" onClick={handleDelete} loading={deleting} disabled={!patientId}>
            <Trash2 size={15} /> Forget
          </Button>
        </div>
      </div>

      {loading && (<><CardSkeleton /><CardSkeleton /></>)}

      {!loading && !patients.length && (
        <EmptyState
          icon={Brain}
          title="No patient memory yet"
          description="Chat with the Copilot Workspace or analyse a prescription for a named patient — remembered context builds automatically."
        />
      )}

      {!loading && profile && (
        <>
          <Card className="flex flex-wrap items-center gap-4">
            <div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-primary-soft text-primary">
              <User size={26} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-lg font-semibold text-foreground">{profile.patient_name}</p>
              <p className="text-sm text-muted">
                {profile.age != null ? `${profile.age} yrs` : 'Age unknown'}
                {profile.gender ? ` · ${profile.gender}` : ''} · {profile.event_count} remembered event(s)
              </p>
            </div>
            {profile.allergies?.length > 0 && (
              <Badge tone="danger"><ShieldAlert size={12} /> {profile.allergies.length} allerg{profile.allergies.length === 1 ? 'y' : 'ies'}</Badge>
            )}
          </Card>

          {/* AI summary */}
          <Card className="border-primary/20 bg-primary-soft/30">
            <CardHeader
              icon={Sparkles}
              title="AI Summary"
              subtitle={profile.last_summary_at ? `Updated ${formatDate(profile.last_summary_at)}` : 'No summary generated yet'}
            />
            <p className="text-sm text-foreground">
              {profile.last_summary || 'Not enough conversation yet to summarize. Keep chatting and a running summary will appear here automatically.'}
            </p>
          </Card>

          {/* Profile facts */}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader icon={Pill} title="Current Medicines" />
              {profile.current_medicines?.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {profile.current_medicines.map((m) => <Badge key={m} tone="primary">{m}</Badge>)}
                </div>
              ) : <p className="text-sm text-muted">No medicines on record.</p>}
            </Card>
            <Card>
              <CardHeader icon={Stethoscope} title="Known Conditions" />
              {profile.known_conditions?.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {profile.known_conditions.map((c) => <Badge key={c} tone="neutral">{c}</Badge>)}
                </div>
              ) : <p className="text-sm text-muted">No conditions on record.</p>}
            </Card>
          </div>

          {/* Conversation history */}
          <Card>
            <CardHeader icon={MessageSquareText} title="Conversation History" subtitle="Every remembered chat turn with the AI Copilot" />
            <ConversationThread messages={detail.conversation} />
          </Card>

          {/* OCR + Medicine + Disease timelines */}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader icon={ScanLine} title="OCR History" />
              <EventTimeline events={detail.ocr_history} dotColor="var(--success)" emptyText="No prescriptions analysed yet." />
            </Card>
            <Card>
              <CardHeader icon={Pill} title="Medicine Timeline" />
              <EventTimeline events={detail.medicine_timeline} dotColor="var(--primary)" emptyText="No medicines remembered yet." />
            </Card>
            <Card>
              <CardHeader icon={Stethoscope} title="Disease Prediction Timeline" />
              <EventTimeline events={detail.disease_timeline} dotColor="var(--warning)" emptyText="No disease predictions remembered yet." />
            </Card>
            <Card>
              <CardHeader icon={ShieldAlert} title="Drug Interaction History" />
              <EventTimeline events={detail.interaction_history} dotColor="var(--danger)" emptyText="No interaction checks remembered yet." />
            </Card>
          </div>

          {/* Follow-up recommendations */}
          <Card>
            <CardHeader icon={ClipboardList} title="Follow-up Recommendations" subtitle="Open action items for this patient" />
            {profile.follow_up_recommendations?.length ? (
              <ul className="space-y-1.5">
                {profile.follow_up_recommendations.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm text-foreground">
                    <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />{r}
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No open follow-ups.</p>}
          </Card>
        </>
      )}
    </div>
  )
}
