import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  ScanLine,
  UploadCloud,
  Camera,
  X,
  FileDown,
  Pill,
  AlertTriangle,
  StickyNote,
  Loader2,
  CheckCircle2,
  ShieldCheck,
  RotateCcw,
  Settings2,
  Activity,
  HeartPulse,
  Pencil,
  Check,
  Trash2,
  UserRound,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import Accordion from '@/ui/Accordion'
import EmptyState from '@/ui/EmptyState'
import { extractPrescription } from '@/lib/api'
import { saveReport } from '@/lib/storage'
import { errorMessage, isCanceled, titleCase, confidenceColor } from '@/lib/utils'

const VERIFY_BELOW = 70

const DISCLAIMER =
  'This is an AI-assisted transcription of a prescription and may contain errors. ' +
  'Always verify against the original prescription and consult a licensed pharmacist ' +
  'or doctor before taking any medication.'

const pct = (v) => Math.round((v || 0) * 100)
const freqText = (m) => m.frequency_expanded || titleCase(m.frequency || '') || null

function readAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result)
    r.onerror = reject
    r.readAsDataURL(file)
  })
}

// ============================================================
//  PDF report (uses edited medicines + structured fields)
// ============================================================
async function generatePdf({ meds, fields, score, imageDataUrl, fileName, notes }) {
  const { jsPDF } = await import('jspdf')
  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  const W = doc.internal.pageSize.getWidth()
  const H = doc.internal.pageSize.getHeight()
  const M = 40
  let y = M
  const ensure = (s) => { if (y + s > H - M) { doc.addPage(); y = M } }
  const line = (txt, { size = 11, color = [40, 40, 40], gap = 16, bold = false } = {}) => {
    doc.setFont('helvetica', bold ? 'bold' : 'normal')
    doc.setFontSize(size)
    doc.setTextColor(...color)
    doc.splitTextToSize(txt, W - M * 2).forEach((l) => { ensure(gap); doc.text(l, M, y); y += gap })
  }

  doc.setFillColor(37, 99, 235)
  doc.rect(0, 0, W, 70, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFont('helvetica', 'bold'); doc.setFontSize(20); doc.text('MediSense', M, 34)
  doc.setFont('helvetica', 'normal'); doc.setFontSize(11); doc.text('Prescription Analysis Report', M, 52)
  doc.setFontSize(9); doc.text(new Date().toLocaleString(), W - M, 34, { align: 'right' })
  y = 92

  // Patient / visit
  const f = fields || {}
  const head = [
    f.doctor && `Doctor: ${f.doctor}`,
    f.hospital && `Clinic: ${f.hospital}`,
    f.patient && `Patient: ${f.patient}`,
    (f.age || f.gender) && `Age/Sex: ${[f.age, f.gender].filter(Boolean).join(' / ')}`,
    f.date && `Date: ${f.date}`,
    f.diagnosis && `Diagnosis: ${f.diagnosis}`,
  ].filter(Boolean)
  head.forEach((h) => line(h, { size: 10, color: [70, 70, 70], gap: 15 }))
  const vit = Object.entries(f.vitals || {})
  if (vit.length) line('Vitals: ' + vit.map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join('   '), { size: 10, color: [70, 70, 70], gap: 16 })

  line(`Medicines detected: ${meds.length}    Overall confidence: ${score}%`, { size: 12, bold: true, gap: 20 })

  if (imageDataUrl) {
    try {
      const props = doc.getImageProperties(imageDataUrl)
      const w = 190
      const h = (props.height / props.width) * w
      ensure(h + 16)
      line('Uploaded prescription:', { size: 10, color: [120, 120, 120], gap: 14 })
      doc.addImage(imageDataUrl, props.fileType, M, y, w, h); y += h + 18
    } catch { /* skip */ }
  }

  line('Medicines', { size: 14, bold: true, gap: 20, color: [37, 99, 235] })
  meds.forEach((m, i) => {
    ensure(40)
    const name = m.name ? titleCase(m.name) : m.raw_text
    line(`${i + 1}. ${name}   (${pct(m.confidence)}%)`, { size: 12, bold: true, gap: 16 })
    line(`Dosage: ${m.dosage || '-'}    Frequency: ${freqText(m) || '-'}    Duration: ${m.duration || '-'}`,
      { size: 10, color: [80, 80, 80], gap: 15 })
    if (m.details?.uses?.length) line(`Uses: ${m.details.uses.slice(0, 3).join(', ')}`, { size: 10, color: [80, 80, 80], gap: 15 })
    if (m.details?.side_effects?.length) line(`Side effects: ${m.details.side_effects.slice(0, 5).join(', ')}`, { size: 10, color: [80, 80, 80], gap: 15 })
    y += 6
  })

  if (notes?.length) {
    y += 4; line("Doctor's notes", { size: 12, bold: true, gap: 16 })
    notes.forEach((n) => line(`- ${n}`, { size: 10, color: [80, 80, 80], gap: 15 }))
  }

  y += 10; ensure(60); doc.setDrawColor(220); doc.line(M, y, W - M, y); y += 16
  line(DISCLAIMER, { size: 9, color: [130, 130, 130], gap: 13 })
  doc.save(`medisense-report-${(fileName || 'prescription').replace(/\.[^.]+$/, '')}.pdf`)
}

// ============================================================
//  Components
// ============================================================
function BulletList({ items }) {
  return (
    <ul className="mt-1 space-y-1">
      {items.map((it, i) => (
        <li key={i} className="flex gap-2 text-sm text-muted">
          <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
          <span>{titleCase(String(it))}</span>
        </li>
      ))}
    </ul>
  )
}

function EditField({ label, value, onChange }) {
  return (
    <label className="block">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</span>
      <input
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 h-9 w-full rounded-lg border border-border bg-background px-2 text-sm text-foreground outline-none focus:border-primary"
      />
    </label>
  )
}

function MedicineCard({ med, editing, onChange, onRemove }) {
  const conf = pct(med.confidence)
  const low = med.needs_review || conf < VERIFY_BELOW
  const name = med.name ? titleCase(med.name) : med.raw_text
  const d = med.details

  if (editing) {
    return (
      <Card className="animate-fade-up border-primary/30">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-primary">Editing</span>
          <button onClick={onRemove} aria-label="Remove medicine" className="text-muted hover:text-danger">
            <Trash2 size={16} />
          </button>
        </div>
        <div className="mt-3 space-y-3">
          <EditField label="Medicine name" value={med.name || med.raw_text} onChange={(v) => onChange({ name: v })} />
          {med.candidates?.length > 1 && (
            <div>
              <span className="text-[11px] font-medium uppercase tracking-wide text-muted">Pick a match</span>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {med.candidates.map((c) => (
                  <button
                    key={c.name}
                    onClick={() => onChange({ name: c.name })}
                    className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-foreground hover:bg-primary-soft hover:text-primary"
                  >
                    {titleCase(c.name)} · {c.score.toFixed(0)}%
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="grid grid-cols-3 gap-2">
            <EditField label="Dosage" value={med.dosage} onChange={(v) => onChange({ dosage: v })} />
            <EditField label="Frequency" value={freqText(med)} onChange={(v) => onChange({ frequency_expanded: v })} />
            <EditField label="Duration" value={med.duration} onChange={(v) => onChange({ duration: v })} />
          </div>
        </div>
      </Card>
    )
  }

  return (
    <Card className="animate-fade-up">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-primary-soft text-primary">
            <Pill size={22} />
          </span>
          <h3 className="text-xl font-bold leading-tight text-foreground">{name}</h3>
        </div>
        <span
          className="shrink-0 rounded-full px-3 py-1 text-xs font-semibold"
          style={{ color: confidenceColor(conf), backgroundColor: `${confidenceColor(conf)}1a` }}
        >
          {conf}%
        </span>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-3 text-center">
        {[['Dosage', med.dosage], ['Frequency', freqText(med)], ['Duration', med.duration]].map(([label, val]) => (
          <div key={label} className="rounded-xl bg-surface-2 p-3">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
            <p className="mt-1 text-sm font-semibold text-foreground">{val || '—'}</p>
          </div>
        ))}
      </div>

      {(d?.uses?.length || d?.side_effects?.length) && (
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          {d?.uses?.length > 0 && (
            <div>
              <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                <Activity size={15} className="text-primary" /> Uses
              </p>
              <BulletList items={d.uses.slice(0, 3)} />
            </div>
          )}
          {d?.side_effects?.length > 0 && (
            <div>
              <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                <HeartPulse size={15} className="text-primary" /> Common side effects
              </p>
              <BulletList items={d.side_effects.slice(0, 5)} />
            </div>
          )}
        </div>
      )}

      {low && (
        <div className="mt-5 flex items-start gap-2 rounded-xl bg-warning/10 p-3 text-sm text-foreground">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
          <span>Please verify this medicine manually before relying on the result.</span>
        </div>
      )}
    </Card>
  )
}

function PatientCard({ fields, editing, onChange }) {
  const f = fields || {}
  const rows = [
    ['doctor', 'Doctor'], ['hospital', 'Clinic / Hospital'], ['patient', 'Patient'],
    ['age', 'Age'], ['gender', 'Gender'], ['date', 'Date'], ['diagnosis', 'Diagnosis'],
    ['advice', 'Advice'], ['follow_up', 'Follow-up'], ['investigations', 'Investigations'],
  ]
  const present = rows.filter(([k]) => f[k])
  const vitals = Object.entries(f.vitals || {})
  if (!editing && !present.length && !vitals.length) return null

  return (
    <Card>
      <CardHeader icon={UserRound} title="Patient & Visit Details" subtitle="Parsed from the prescription" />
      {editing ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {rows.map(([k, label]) => (
            <EditField key={k} label={label} value={f[k]} onChange={(v) => onChange({ ...f, [k]: v })} />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {present.map(([k, label]) => (
            <div key={k} className="rounded-xl bg-surface-2 p-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
              <p className="mt-0.5 text-sm font-semibold text-foreground">{f[k]}</p>
            </div>
          ))}
          {vitals.length > 0 && (
            <div className="rounded-xl bg-surface-2 p-3 sm:col-span-2">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Vitals</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {vitals.map(([k, v]) => (
                  <Badge key={k} tone="primary">{k.replace(/_/g, ' ')}: {v}</Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ============================================================
//  Page
// ============================================================
export default function PrescriptionOCR() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [imageDataUrl, setImageDataUrl] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState(0)
  const [processing, setProcessing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [meds, setMeds] = useState([])          // editable copy
  const [fields, setFields] = useState({})      // editable copy
  const [editing, setEditing] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const inputRef = useRef(null)
  const cameraRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    if (result) {
      setMeds(result.medicines || [])
      setFields(result.fields || {})
      setEditing(false)
    }
  }, [result])

  // Elapsed-time counter so the user sees progress during slow OCR.
  useEffect(() => {
    if (!processing) return
    setElapsed(0)
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [processing])

  const pickFile = async (f) => {
    if (!f) return
    if (!f.type.startsWith('image/')) return toast.error('Please choose an image file')
    setFile(f); setPreview(URL.createObjectURL(f)); setResult(null); setError(null)
    try { setImageDataUrl(await readAsDataUrl(f)) } catch { setImageDataUrl(null) }
  }
  const onDrop = (e) => { e.preventDefault(); setDragOver(false); pickFile(e.dataTransfer.files?.[0]) }
  const reset = () => { setFile(null); setPreview(null); setImageDataUrl(null); setResult(null); setError(null); setProgress(0) }

  const run = async () => {
    if (!file) return
    const controller = new AbortController()
    abortRef.current = controller
    setProcessing(true); setError(null); setResult(null); setProgress(0)
    try {
      const data = await extractPrescription(file, {
        onProgress: setProgress,
        signal: controller.signal,
      })
      setResult(data)
      saveReport({ fileName: file.name, provider: data.provider, medicineCount: data.medicines?.length || 0, overall: data.overall_confidence })
    } catch (err) {
      // A user-initiated cancel is NOT an error — stay silent and reset.
      if (!isCanceled(err)) {
        setError(errorMessage(err, 'We could not analyze this prescription. Please try again.'))
      }
    } finally {
      setProcessing(false)
      abortRef.current = null
    }
  }

  const cancel = () => abortRef.current?.abort()

  const updateMed = (i, patch) => setMeds((prev) => prev.map((m, idx) => (idx === i ? { ...m, ...patch } : m)))
  const removeMed = (i) => setMeds((prev) => prev.filter((_, idx) => idx !== i))

  const score = result
    ? pct(result.overall_confidence) || (meds.length ? Math.round(meds.reduce((a, m) => a + (m.confidence || 0), 0) / meds.length * 100) : 0)
    : 0
  const needsVerify = result && (score < VERIFY_BELOW || meds.some((m) => m.needs_review))

  const downloadReport = async () => {
    try {
      await generatePdf({ meds, fields, score, imageDataUrl, fileName: file?.name, notes: result?.doctor_notes })
    } catch {
      toast.error('Could not generate the report')
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      {/* Upload panel */}
      <div className="lg:col-span-2">
        <Card className="lg:sticky lg:top-24">
          <CardHeader icon={ScanLine} title="Scan a Prescription" subtitle="Upload a photo — handwritten or printed" />
          {!preview ? (
            <div
              role="button" tabIndex={0}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-10 text-center transition-colors ${
                dragOver ? 'border-primary bg-primary-soft' : 'border-border hover:border-primary/50 hover:bg-surface-2'
              }`}
            >
              <span className="grid h-14 w-14 place-items-center rounded-2xl bg-primary-soft text-primary"><UploadCloud size={26} /></span>
              <p className="mt-3 font-medium text-foreground">Drag & drop, or click to browse</p>
              <p className="mt-1 text-xs text-muted">PNG, JPG, WEBP</p>
            </div>
          ) : (
            <div className="relative overflow-hidden rounded-2xl border border-border">
              <img src={preview} alt="Prescription preview" className="max-h-72 w-full bg-surface-2 object-contain" />
              <button onClick={reset} aria-label="Remove image" className="absolute right-2 top-2 grid h-8 w-8 place-items-center rounded-full bg-black/60 text-white hover:bg-black/80"><X size={16} /></button>
              {processing && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/85 backdrop-blur-sm">
                  <Loader2 size={32} className="animate-spin text-primary" />
                  <p className="text-sm font-medium text-foreground">{progress < 100 ? `Uploading ${progress}%` : 'Analyzing prescription…'}</p>
                  <Button size="sm" variant="secondary" onClick={cancel}><X size={14} /> Cancel</Button>
                </div>
              )}
            </div>
          )}
          <input ref={inputRef} type="file" accept="image/*" hidden onChange={(e) => pickFile(e.target.files?.[0])} />
          <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => pickFile(e.target.files?.[0])} />
          <div className="mt-4 flex gap-2">
            <Button className="flex-1" onClick={run} loading={processing} disabled={!file}><ScanLine size={16} /> Analyze</Button>
            <Button variant="secondary" onClick={() => cameraRef.current?.click()} aria-label="Use camera"><Camera size={16} /></Button>
          </div>
          <p className="mt-3 text-xs text-muted">For best results: good lighting, a flat page, and the whole prescription in frame.</p>
        </Card>
      </div>

      {/* Results */}
      <div className="space-y-5 lg:col-span-3">
        {processing && (
          <Card className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <Loader2 size={30} className="animate-spin text-primary" />
            <p className="font-medium text-foreground">Analyzing your prescription…</p>
            <p className="text-sm text-muted">
              {progress < 100 ? `Uploading image… ${progress}%` : 'Reading handwriting and matching medicines'}
              {' · '}{elapsed}s elapsed
            </p>
            <p className="text-xs text-muted">Handwriting OCR can take a minute or two. Please keep this tab open.</p>
            <Button variant="secondary" size="sm" onClick={cancel}><X size={14} /> Cancel</Button>
          </Card>
        )}

        {!processing && error && (
          <Card className="border-danger/30 bg-danger/5">
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <span className="grid h-14 w-14 place-items-center rounded-2xl bg-danger/15 text-danger"><AlertTriangle size={26} /></span>
              <h3 className="text-lg font-semibold text-foreground">Analysis failed</h3>
              <p className="max-w-sm text-sm text-muted">{error}</p>
              <Button variant="secondary" onClick={run} disabled={!file}><RotateCcw size={15} /> Try again</Button>
            </div>
          </Card>
        )}

        {!processing && !error && !result && (
          <EmptyState
            icon={Pill}
            title="Your medicines will appear here"
            description="Upload a prescription and tap Analyze. We’ll list each medicine with its dosage, schedule, uses and side effects — and let you correct anything."
          />
        )}

        {!processing && result && (
          <>
            <Card className="border-success/30 bg-success/5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <span className="grid h-12 w-12 place-items-center rounded-2xl bg-success/15 text-success"><CheckCircle2 size={26} /></span>
                  <div>
                    <h2 className="text-lg font-bold text-foreground">Prescription Analysis Complete</h2>
                    <p className="text-sm text-muted">Medicines found: <span className="font-semibold text-foreground">{meds.length}</span></p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-xs text-muted">Confidence Score</p>
                    <p className="text-2xl font-bold" style={{ color: confidenceColor(score) }}>{score}%</p>
                  </div>
                  <Button variant={editing ? 'primary' : 'secondary'} size="sm" onClick={() => setEditing((e) => !e)}>
                    {editing ? <><Check size={15} /> Done</> : <><Pencil size={15} /> Edit</>}
                  </Button>
                  <Button variant="secondary" size="sm" onClick={downloadReport}><FileDown size={15} /> Report</Button>
                </div>
              </div>
              {needsVerify && (
                <div className="mt-4 flex items-start gap-2 rounded-xl bg-warning/10 p-3 text-sm text-foreground">
                  <ShieldCheck size={16} className="mt-0.5 shrink-0 text-warning" />
                  <span><span className="font-semibold">Manual verification recommended.</span> Confirm the medicines below, then tap <span className="font-semibold">Edit</span> to correct anything.</span>
                </div>
              )}
            </Card>

            <PatientCard fields={fields} editing={editing} onChange={setFields} />

            {meds.length === 0 ? (
              <EmptyState icon={ScanLine} title="No medicines detected" description="Try a clearer, well-lit photo of the full prescription." />
            ) : (
              <div className="grid gap-5">
                {meds.map((m, i) => (
                  <MedicineCard key={i} med={m} editing={editing} onChange={(patch) => updateMed(i, patch)} onRemove={() => removeMed(i)} />
                ))}
              </div>
            )}

            {result.doctor_notes?.length > 0 && (
              <Card>
                <CardHeader icon={StickyNote} title="Doctor’s Notes" />
                <ul className="space-y-1.5 text-sm text-foreground">
                  {result.doctor_notes.map((n, i) => (
                    <li key={i} className="flex gap-2"><span className="text-primary">•</span>{n}</li>
                  ))}
                </ul>
              </Card>
            )}

            <Accordion title="Advanced Information" subtitle="OCR engines, alternative matches, drug classes & raw text" icon={Settings2}>
              <div className="space-y-6 text-sm">
                {meds.map((m, i) => {
                  const d = m.details
                  const alts = (m.candidates || []).slice(1)
                  const hasClasses = d && (d.therapeutic_class || d.chemical_class || d.action_class)
                  if (!alts.length && !hasClasses && !d?.substitutes?.length) return null
                  return (
                    <div key={i} className="border-b border-border pb-4 last:border-0 last:pb-0">
                      <p className="font-semibold text-foreground">
                        {m.name ? titleCase(m.name) : m.raw_text}
                        <span className="ml-2 text-xs font-normal text-muted">match score {(m.candidates?.[0]?.score ?? 0).toFixed(0)}%</span>
                      </p>
                      {alts.length > 0 && (
                        <p className="mt-1 text-muted"><span className="font-medium text-foreground">Alternative matches: </span>{alts.map((c) => `${titleCase(c.name)} (${c.score.toFixed(0)}%)`).join(', ')}</p>
                      )}
                      {hasClasses && (
                        <p className="mt-1 text-muted"><span className="font-medium text-foreground">Classification: </span>{[d.therapeutic_class, d.chemical_class, d.action_class].filter((x) => x && x !== 'NA').join(' · ')}</p>
                      )}
                      {d?.substitutes?.length > 0 && (
                        <p className="mt-1 text-muted"><span className="font-medium text-foreground">Substitutes: </span>{d.substitutes.slice(0, 5).join(', ')}</p>
                      )}
                    </div>
                  )
                })}

                {result.engines && Object.keys(result.engines).length > 0 && (
                  <div>
                    <p className="mb-1 font-medium text-foreground">OCR engines compared</p>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(result.engines).map(([name, info]) => (
                        <Badge key={name} tone={name === result.best_engine ? 'success' : 'neutral'}>
                          {name}: {(info.score * 100).toFixed(0)}%{name === result.best_engine ? ' ✓' : ''}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                <div className="text-muted">
                  <span className="font-medium text-foreground">Engine used: </span>{result.provider} ·{' '}
                  <span className="font-medium text-foreground">overall confidence: </span>{pct(result.overall_confidence)}%
                </div>

                {result.raw_text && (
                  <div>
                    <p className="mb-1 font-medium text-foreground">Raw OCR text</p>
                    <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-surface-2 p-3 text-xs text-muted">{result.raw_text}</pre>
                  </div>
                )}
              </div>
            </Accordion>

            <p className="px-2 text-center text-xs text-muted">{DISCLAIMER}</p>
          </>
        )}
      </div>
    </div>
  )
}
