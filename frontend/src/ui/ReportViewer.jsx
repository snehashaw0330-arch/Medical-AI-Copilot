import {
  FileText,
  Pill,
  Activity,
  HeartPulse,
  Stethoscope,
  Lightbulb,
  AlertTriangle,
  Ban,
  CalendarClock,
  BookOpen,
  Clock,
  Gauge,
  Cpu,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Badge from '@/ui/Badge'
import Accordion from '@/ui/Accordion'
import ClinicalReport from '@/ui/ClinicalReport'
import DrugInteractionReport from '@/ui/DrugInteractionReport'
import { reportImageUrl } from '@/lib/api'
import { titleCase, confidenceColor, pct, formatDate } from '@/lib/utils'

/**
 * Medical Report Viewer — renders the backend `ReportContent` (Requirement 7).
 *
 * Pure presentation. It reuses the existing `ClinicalReport` and
 * `DrugInteractionReport` components for those sections (no duplicated UI): when
 * the report carries a clinical sub-report, that component already renders the
 * disease prediction, risks, interactions and sources, so the viewer only adds
 * the report-specific sections (image, OCR text, medicines, RAG documents).
 *
 * Props:
 *   report   — a ReportDetail `{ id, created_at, content }` (or just `content`)
 */

function MetaTile({ icon: Icon, label, value, color }) {
  return (
    <div className="rounded-xl bg-surface-2 p-3 text-center">
      <p className="flex items-center justify-center gap-1 text-[11px] font-medium uppercase tracking-wide text-muted">
        <Icon size={12} /> {label}
      </p>
      <p className="mt-1 text-lg font-bold" style={{ color: color || 'var(--foreground)' }}>{value}</p>
    </div>
  )
}

function MedicineBlock({ m }) {
  const conf = pct(m.confidence)
  const name = m.name ? titleCase(m.name) : m.raw_text
  const alts = (m.candidates || []).slice(1, 4).filter((c) => c.name)
  return (
    <div className="rounded-xl bg-surface-2 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold text-foreground">
          <Pill size={16} className="text-primary" /> {name}
        </p>
        <span className="text-xs font-semibold" style={{ color: confidenceColor(conf) }}>{conf}%</span>
      </div>
      <p className="mt-1 text-xs text-muted">
        Dosage: {m.dosage || '—'} · Frequency: {m.frequency || '—'} · Duration: {m.duration || '—'}
      </p>
      {m.needs_review && (
        <p className="mt-1 flex items-center gap-1 text-xs text-warning">
          <AlertTriangle size={12} /> Low confidence — verify manually.
        </p>
      )}
      {alts.length > 0 && (
        <p className="mt-1 text-xs text-muted">
          <span className="font-medium text-foreground">Alternatives: </span>
          {alts.map((c) => `${titleCase(c.name)} (${Math.round(c.score)}%)`).join(', ')}
        </p>
      )}
      {(m.uses?.length || m.side_effects?.length) > 0 && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {m.uses?.length > 0 && (
            <p className="text-xs text-muted">
              <span className="flex items-center gap-1 font-medium text-foreground"><Activity size={12} className="text-primary" /> Uses</span>
              {m.uses.slice(0, 3).join(', ')}
            </p>
          )}
          {m.side_effects?.length > 0 && (
            <p className="text-xs text-muted">
              <span className="flex items-center gap-1 font-medium text-foreground"><HeartPulse size={12} className="text-primary" /> Side effects</span>
              {m.side_effects.slice(0, 4).join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function ListCard({ icon: Icon, title, items, accent = 'bg-primary' }) {
  if (!items?.length) return null
  return (
    <Card>
      <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon size={15} className="text-primary" /> {title}
      </p>
      <ul className="mt-2 space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-sm text-foreground">
            <span className={`mt-2 h-1 w-1 shrink-0 rounded-full ${accent}`} />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

export default function ReportViewer({ report }) {
  if (!report) return null
  const content = report.content || report
  const id = report.id
  const conf = pct(content.overall_confidence)
  const meds = content.medicines || []
  const patient = content.patient || {}
  const clinical = content.clinical
  const hasImage = content.has_image && id

  const patientRows = [
    ['Patient', patient.name], ['Age', patient.age], ['Gender', patient.gender],
    ['Doctor', patient.doctor], ['Hospital', patient.hospital],
    ['Date', patient.date], ['Diagnosis', patient.diagnosis],
  ].filter(([, v]) => v)

  return (
    <div className="space-y-5">
      {/* ---- Header ---- */}
      <Card>
        <CardHeader
          icon={FileText}
          title={content.title || 'Medical Analysis Report'}
          subtitle={content.filename || 'Prescription analysis'}
        />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetaTile icon={Gauge} label="OCR confidence" value={`${conf}%`} color={confidenceColor(conf)} />
          <MetaTile icon={Pill} label="Medicines" value={meds.length} />
          <MetaTile icon={Clock} label="Processing" value={`${content.processing_time || 0}s`} />
          <MetaTile icon={Cpu} label="Engine" value={content.provider || content.engine || '—'} />
        </div>
        <p className="mt-3 text-xs text-muted">
          Generated {content.timestamp || (report.created_at && formatDate(report.created_at))}
        </p>
      </Card>

      {/* ---- Prescription image + OCR text ---- */}
      {(hasImage || content.raw_text) && (
        <Card>
          <CardHeader icon={FileText} title="Prescription & OCR Text" />
          <div className="grid gap-5 md:grid-cols-2">
            {hasImage && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Uploaded prescription</p>
                <img
                  src={reportImageUrl(id)}
                  alt="Prescription"
                  className="max-h-80 w-full rounded-xl border border-border bg-surface-2 object-contain"
                />
              </div>
            )}
            <div className={hasImage ? '' : 'md:col-span-2'}>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">OCR extracted text</p>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-xl bg-surface-2 p-3 text-xs text-muted">
                {content.raw_text || 'No text extracted.'}
              </pre>
            </div>
          </div>
        </Card>
      )}

      {/* ---- Patient information ---- */}
      {patientRows.length > 0 && (
        <Card>
          <CardHeader icon={Stethoscope} title="Patient Information" />
          <div className="grid gap-3 sm:grid-cols-2">
            {patientRows.map(([k, v]) => (
              <div key={k} className="rounded-xl bg-surface-2 p-3">
                <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{k}</p>
                <p className="mt-0.5 text-sm font-semibold text-foreground">{v}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ---- Medicines ---- */}
      {meds.length > 0 && (
        <Card>
          <CardHeader icon={Pill} title="Medicines Detected" subtitle={`${meds.length} medicine(s) with confidence scores`} />
          <div className="grid gap-2">
            {meds.map((m, i) => <MedicineBlock key={i} m={m} />)}
          </div>
        </Card>
      )}

      {/* ---- Clinical decision report (reused component: covers disease
              prediction, risks, interactions, sources when present) ---- */}
      {clinical ? (
        <ClinicalReport report={clinical} />
      ) : (
        <>
          {content.drug_interactions && <DrugInteractionReport report={content.drug_interactions} />}
          <ListCard icon={Lightbulb} title="AI Recommendations" items={content.recommendations} />
          <ListCard icon={AlertTriangle} title="Warnings" items={content.warnings} accent="bg-warning" />
          <ListCard icon={Ban} title="Contraindications" items={content.contraindications} accent="bg-danger" />
          <ListCard icon={CalendarClock} title="Follow-up Suggestions" items={content.follow_up} />
        </>
      )}

      {/* ---- Retrieved RAG documents + sources ---- */}
      {(content.rag_documents?.length > 0 || content.sources?.length > 0) && (
        <Accordion title="Retrieved Knowledge & Sources" subtitle="RAG context and provenance" icon={BookOpen}>
          {content.rag_documents?.map((d, i) => (
            <div key={i} className="mb-3 rounded-xl bg-surface-2 p-3">
              {d.source && <p className="text-xs font-medium text-foreground">Source: {d.source}</p>}
              {d.text && <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{d.text}</p>}
            </div>
          ))}
          {content.sources?.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {content.sources.map((s, i) => <Badge key={i} tone="neutral">{s}</Badge>)}
            </div>
          )}
        </Accordion>
      )}

      {content.disclaimer && (
        <p className="px-2 text-center text-xs text-muted">{content.disclaimer}</p>
      )}
    </div>
  )
}
