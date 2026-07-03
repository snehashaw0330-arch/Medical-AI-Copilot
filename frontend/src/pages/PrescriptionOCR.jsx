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
  RefreshCw,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import Accordion from '@/ui/Accordion'
import EmptyState from '@/ui/EmptyState'
import QualityReport from '@/ui/QualityReport'
import DrugInteractionReport from '@/ui/DrugInteractionReport'
import ClinicalReport from '@/ui/ClinicalReport'
import { extractPrescription, assessImageQuality, checkInteractions } from '@/lib/api'
import { saveReport } from '@/lib/storage'
import { errorMessage, isCanceled, titleCase, confidenceColor, pct, freqText } from '@/lib/utils'
import { generatePrescriptionPdf, readFileAsDataUrl, DISCLAIMER } from '@/lib/pdf'

const VERIFY_BELOW = 70

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
  const [assessing, setAssessing] = useState(false)
  const [quality, setQuality] = useState(null)     // image-quality report
  const [qualityGate, setQualityGate] = useState(false)  // low quality, awaiting user
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [meds, setMeds] = useState([])          // editable copy
  const [fields, setFields] = useState({})      // editable copy
  const [editing, setEditing] = useState(false)
  const [interactions, setInteractions] = useState(null)  // drug interaction report
  const [clinical, setClinical] = useState(null)          // clinical decision report
  const [rechecking, setRechecking] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const inputRef = useRef(null)
  const cameraRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    if (result) {
      setMeds(result.medicines || [])
      setFields(result.fields || {})
      setEditing(false)
      // The backend auto-runs interaction analysis when >=2 medicines are found
      // and ships it inline on the OCR result.
      setInteractions(result.drug_interactions || null)
      // The backend also runs clinical decision support (OCR -> matching ->
      // interactions -> RAG -> CDSS) and ships the report inline.
      setClinical(result.clinical_report || null)
    }
  }, [result])

  // Re-run interaction analysis against the (possibly edited) medicine list.
  const recheckInteractions = async () => {
    const names = meds.map((m) => m.name).filter(Boolean)
    if (names.length < 2) {
      toast.error('Add at least two recognised medicines to check interactions.')
      return
    }
    setRechecking(true)
    try {
      setInteractions(await checkInteractions(names))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not check drug interactions.'))
    } finally {
      setRechecking(false)
    }
  }

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
    setQuality(null); setQualityGate(false)
    try { setImageDataUrl(await readFileAsDataUrl(f)) } catch { setImageDataUrl(null) }
  }
  const onDrop = (e) => { e.preventDefault(); setDragOver(false); pickFile(e.dataTransfer.files?.[0]) }
  const reset = () => {
    setFile(null); setPreview(null); setImageDataUrl(null); setResult(null); setError(null)
    setProgress(0); setQuality(null); setQualityGate(false)
  }

  // Run the actual OCR pipeline.
  const runOcr = async () => {
    if (!file) return
    setQualityGate(false)
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

  // Entry point from the "Analyze" button: assess quality first, then either
  // proceed to OCR (good image) or gate on user confirmation (low quality).
  const run = async () => {
    if (!file) return
    setError(null); setResult(null); setQuality(null); setQualityGate(false)
    setAssessing(true)
    let report = null
    try {
      report = await assessImageQuality(file)
      setQuality(report)
    } catch (err) {
      // Quality check is best-effort — never block OCR if it fails.
      if (isCanceled(err)) { setAssessing(false); return }
    } finally {
      setAssessing(false)
    }
    // Warn (and wait) only when we got a report saying quality is too low.
    if (report && report.passed === false) {
      setQualityGate(true)
      toast.error(`Low image quality (${Math.round(report.overall_score)}%). Please review before continuing.`)
      return
    }
    await runOcr()
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
      await generatePrescriptionPdf({ meds, fields, score, imageDataUrl, fileName: file?.name, notes: result?.doctor_notes })
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
            <Button className="flex-1" onClick={run} loading={processing || assessing} disabled={!file}>
              <ScanLine size={16} /> {assessing ? 'Checking quality…' : 'Analyze'}
            </Button>
            <Button variant="secondary" onClick={() => cameraRef.current?.click()} aria-label="Use camera"><Camera size={16} /></Button>
          </div>
          <p className="mt-3 text-xs text-muted">For best results: good lighting, a flat page, and the whole prescription in frame.</p>
        </Card>
      </div>

      {/* Results */}
      <div className="space-y-5 lg:col-span-3">
        {assessing && (
          <Card className="flex flex-col items-center justify-center gap-3 py-12 text-center">
            <Loader2 size={28} className="animate-spin text-primary" />
            <p className="font-medium text-foreground">Assessing image quality…</p>
            <p className="text-sm text-muted">Checking blur, lighting, contrast, resolution and orientation.</p>
          </Card>
        )}

        {/* Image quality report (shown after assessment, persists through OCR). */}
        {!assessing && quality && <QualityReport report={quality} />}

        {/* Low-quality gate: let the user recapture or proceed anyway. */}
        {!assessing && !processing && qualityGate && (
          <Card className="border-warning/40 bg-warning/5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-foreground">
                This image scored below {Math.round(quality?.threshold ?? 60)}%. For the best results, retake the photo
                using the tips above — or continue if you’re sure.
              </p>
              <div className="flex shrink-0 gap-2">
                <Button variant="secondary" size="sm" onClick={reset}><RotateCcw size={15} /> Retake</Button>
                <Button size="sm" onClick={runOcr}><ScanLine size={15} /> Run OCR anyway</Button>
              </div>
            </div>
          </Card>
        )}

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

        {!processing && !assessing && !error && !result && !quality && (
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

            {/* Drug interaction analysis (auto-run after OCR; re-runnable). */}
            {(interactions || meds.filter((m) => m.name).length >= 2) && (
              <div className="space-y-3">
                {interactions ? (
                  <DrugInteractionReport report={interactions} />
                ) : (
                  <EmptyState
                    icon={ShieldCheck}
                    title="Check drug interactions"
                    description="Analyze the detected medicines for drug–drug interactions, severity and clinical warnings."
                  />
                )}
                <div className="flex justify-end">
                  <Button variant="secondary" size="sm" onClick={recheckInteractions} loading={rechecking}>
                    <RefreshCw size={15} /> {interactions ? 'Re-check interactions' : 'Check interactions'}
                  </Button>
                </div>
              </div>
            )}

            {/* Clinical decision support report (auto-run after OCR). The
                interaction card is rendered above, so it is hidden here. */}
            {clinical && <ClinicalReport report={clinical} showInteractions={false} />}

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
