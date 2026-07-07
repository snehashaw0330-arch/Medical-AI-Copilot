import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Layers, Plus, Database, CheckCircle2, X } from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import { CardSkeleton } from '@/ui/Skeleton'
import { getGovernanceDatasets, registerGovernanceDataset } from '@/lib/api'
import { errorMessage, formatDate } from '@/lib/utils'

const EMPTY = { name: '', version: '', source: '', size: '', date_added: '', purpose: '' }
const inputCls = 'h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary'
function Field({ label, children }) {
  return <label className="block"><span className="mb-1 block text-xs font-medium text-muted">{label}</span>{children}</label>
}

function RegisterForm({ onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async () => {
    if (!form.name.trim() || !form.version.trim()) return toast.error('Name and version are required')
    setSaving(true)
    try {
      await registerGovernanceDataset(form)
      toast.success('Dataset registered')
      onSaved()
    } catch (err) {
      toast.error(errorMessage(err, 'Could not register dataset'))
    } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <Card className="w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-bold text-foreground"><Database size={19} className="text-primary" /> Register dataset</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-surface-2"><X size={18} /></button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name *"><input value={form.name} onChange={set('name')} className={inputCls} /></Field>
          <Field label="Version *"><input value={form.version} onChange={set('version')} className={inputCls} /></Field>
          <Field label="Source"><input value={form.source} onChange={set('source')} className={inputCls} /></Field>
          <Field label="Size"><input value={form.size} onChange={set('size')} placeholder="e.g. 18,432 rows" className={inputCls} /></Field>
          <Field label="Date added"><input type="date" value={form.date_added} onChange={set('date_added')} className={inputCls} /></Field>
          <div className="sm:col-span-2">
            <Field label="Purpose"><textarea rows={2} value={form.purpose} onChange={set('purpose')} className={inputCls} /></Field>
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

export default function DatasetRegistry() {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)

  const load = async () => {
    setLoading(true)
    try { setDatasets(await getGovernanceDatasets()) }
    catch (err) { toast.error(errorMessage(err, 'Could not load datasets')) }
    finally { setLoading(false) }
  }
  useEffect(() => {
    let alive = true
    getGovernanceDatasets()
      .then((d) => alive && setDatasets(d))
      .catch((err) => toast.error(errorMessage(err, 'Could not load datasets')))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-foreground"><Layers size={22} className="text-primary" /> Dataset Registry</h1>
          <p className="text-sm text-muted">Every dataset — its version, source, size, date added and purpose.</p>
        </div>
        <Button variant="primary" onClick={() => setShowForm(true)}><Plus size={15} /> Register dataset</Button>
      </div>

      {loading && <div className="grid gap-4 sm:grid-cols-2"><CardSkeleton /><CardSkeleton /></div>}

      {!loading && datasets.length === 0 && (
        <EmptyState icon={Layers} title="No datasets registered" description="Register your first dataset to track provenance and versions." />
      )}

      {!loading && datasets.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {datasets.map((d) => (
            <Card key={`${d.name}@${d.version}`} hover>
              <div className="flex items-start justify-between gap-2">
                <CardHeader icon={Database} title={d.name} subtitle={d.version} />
                {d.size && <Badge tone="primary">{d.size}</Badge>}
              </div>
              {d.purpose && <p className="mb-3 text-sm text-muted">{d.purpose}</p>}
              <dl className="space-y-1.5 text-sm">
                <Row label="Source" value={d.source || '—'} />
                <Row label="Added" value={d.date_added || '—'} />
                <Row label="Updated" value={formatDate(d.updated_at)?.split(',')[0] || '—'} />
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
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="truncate text-right font-medium text-foreground">{value}</dd>
    </div>
  )
}
