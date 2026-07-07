import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Boxes, Plus, Cpu, CheckCircle2, X } from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import { CardSkeleton } from '@/ui/Skeleton'
import { getGovernanceModels, registerGovernanceModel } from '@/lib/api'
import { errorMessage, formatDate } from '@/lib/utils'

const STATUS_TONE = {
  production: 'success', staging: 'primary', experimental: 'warning', deprecated: 'neutral',
}
const STATUSES = ['production', 'staging', 'experimental', 'deprecated']

const EMPTY = { name: '', version: '', accuracy: '', training_date: '', dataset: '', status: 'production', description: '' }

function RegisterForm({ onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async () => {
    if (!form.name.trim() || !form.version.trim()) return toast.error('Name and version are required')
    setSaving(true)
    try {
      await registerGovernanceModel({
        ...form,
        accuracy: form.accuracy === '' ? null : Number(form.accuracy),
      })
      toast.success('Model registered')
      onSaved()
    } catch (err) {
      toast.error(errorMessage(err, 'Could not register model'))
    } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <Card className="w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-bold text-foreground"><Cpu size={19} className="text-primary" /> Register model</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-surface-2"><X size={18} /></button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name *"><input value={form.name} onChange={set('name')} className={inputCls} /></Field>
          <Field label="Version *"><input value={form.version} onChange={set('version')} className={inputCls} /></Field>
          <Field label="Accuracy (0–1)"><input type="number" step="0.001" min="0" max="1" value={form.accuracy} onChange={set('accuracy')} className={inputCls} /></Field>
          <Field label="Training date"><input type="date" value={form.training_date} onChange={set('training_date')} className={inputCls} /></Field>
          <Field label="Dataset"><input value={form.dataset} onChange={set('dataset')} className={inputCls} /></Field>
          <Field label="Status">
            <select value={form.status} onChange={set('status')} className={inputCls}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Description"><textarea rows={2} value={form.description} onChange={set('description')} className={inputCls} /></Field>
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={submit} loading={saving}><CheckCircle2 size={15} /> Save</Button>
        </div>
      </Card>
    </div>
  )
}

const inputCls = 'h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary'
function Field({ label, children }) {
  return <label className="block"><span className="mb-1 block text-xs font-medium text-muted">{label}</span>{children}</label>
}

export default function ModelRegistry() {
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)

  const load = async () => {
    setLoading(true)
    try { setModels(await getGovernanceModels()) }
    catch (err) { toast.error(errorMessage(err, 'Could not load models')) }
    finally { setLoading(false) }
  }
  useEffect(() => {
    let alive = true
    getGovernanceModels()
      .then((d) => alive && setModels(d))
      .catch((err) => toast.error(errorMessage(err, 'Could not load models')))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-foreground"><Boxes size={22} className="text-primary" /> Model Registry</h1>
          <p className="text-sm text-muted">Every AI model, its version, accuracy, source dataset and lifecycle status.</p>
        </div>
        <Button variant="primary" onClick={() => setShowForm(true)}><Plus size={15} /> Register model</Button>
      </div>

      {loading && <div className="grid gap-4 sm:grid-cols-2"><CardSkeleton /><CardSkeleton /></div>}

      {!loading && models.length === 0 && (
        <EmptyState icon={Boxes} title="No models registered" description="Register your first model to start governing versions and accuracy." />
      )}

      {!loading && models.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {models.map((m) => (
            <Card key={`${m.name}@${m.version}`} hover>
              <div className="flex items-start justify-between gap-2">
                <CardHeader icon={Cpu} title={m.name} subtitle={m.version} />
                <Badge tone={STATUS_TONE[m.status] || 'neutral'}>{m.status}</Badge>
              </div>
              {m.description && <p className="mb-3 text-sm text-muted">{m.description}</p>}
              <dl className="space-y-1.5 text-sm">
                <Row label="Accuracy" value={m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : '—'} />
                <Row label="Trained" value={m.training_date || '—'} />
                <Row label="Dataset" value={m.dataset || '—'} />
                <Row label="Updated" value={formatDate(m.updated_at)?.split(',')[0] || '—'} />
              </dl>
            </Card>
          ))}
        </div>
      )}

      {showForm && <RegisterForm onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load() }} />}
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted">{label}</dt>
      <dd className="truncate font-medium text-foreground">{value}</dd>
    </div>
  )
}
