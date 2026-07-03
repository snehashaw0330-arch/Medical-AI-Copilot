import {
  Stethoscope,
  ShieldAlert,
  ShieldCheck,
  AlertOctagon,
  Pill,
  Activity,
  FlaskConical,
  ListChecks,
  CalendarClock,
  HelpCircle,
  Ban,
  BookOpen,
  Gauge,
  Sparkles,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Badge from '@/ui/Badge'
import Accordion from '@/ui/Accordion'
import DrugInteractionReport from '@/ui/DrugInteractionReport'
import { titleCase } from '@/lib/utils'

/**
 * Clinical Decision Report card — the presentation layer for the backend
 * `ClinicalReport` shape produced by backend/clinical_decision/.
 *
 * Pure presentation: it takes a `report` object and renders it. Reused by the
 * dedicated Clinical Decision page, the Prescription OCR results page (inline),
 * and any history detail view — always identical output for the same data.
 *
 * The four-level risk scale maps onto the existing badge tones so the colour
 * language is consistent with the drug-interaction report:
 *   low → primary · moderate → warning · high/critical → danger
 */

// RiskLevel → UI treatment (mirrors backend schemas.RiskLevel ordering).
const RISK = {
  critical: { label: 'Critical', tone: 'danger', color: 'var(--danger)', ring: 'border-danger/40 bg-danger/5', Icon: AlertOctagon },
  high: { label: 'High', tone: 'danger', color: 'var(--danger)', ring: 'border-danger/30 bg-danger/5', Icon: ShieldAlert },
  moderate: { label: 'Moderate', tone: 'warning', color: 'var(--warning)', ring: 'border-warning/30 bg-warning/5', Icon: ShieldAlert },
  low: { label: 'Low', tone: 'primary', color: 'var(--primary)', ring: 'border-primary/30 bg-primary/5', Icon: ShieldCheck },
}

const risk = (r) => RISK[r] || RISK.low

function RiskBadge({ level }) {
  const cfg = risk(level)
  return <Badge tone={cfg.tone}>{cfg.label}</Badge>
}

/** A titled block with an icon and a bulleted list. Renders nothing when empty. */
function ListBlock({ icon: Icon, title, items, tone = 'primary', accent }) {
  if (!items?.length) return null
  const dot = accent || 'bg-primary'
  return (
    <div className="rounded-xl bg-surface-2 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon size={15} style={{ color: `var(--${tone === 'danger' ? 'danger' : tone === 'warning' ? 'warning' : 'primary'})` }} />
        {title}
      </p>
      <ul className="mt-2 space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-sm text-foreground">
            <span className={`mt-2 h-1 w-1 shrink-0 rounded-full ${dot}`} />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RedFlagRow({ flag }) {
  const cfg = risk(flag.severity)
  return (
    <div className={`rounded-xl border p-4 ${cfg.ring}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold text-foreground">
          <AlertOctagon size={16} style={{ color: cfg.color }} />
          {flag.title}
        </p>
        <RiskBadge level={flag.severity} />
      </div>
      {flag.detail && <p className="mt-2 text-sm text-muted">{flag.detail}</p>}
    </div>
  )
}

export default function ClinicalReport({ report, showInteractions = true }) {
  if (!report) return null
  const cfg = risk(report.risk_level)
  const HeaderIcon = cfg.Icon
  const diseases = report.disease_prediction || []
  const redFlags = report.red_flags || []
  const score = Math.round(report.risk_score || 0)
  const confidence = Math.round(report.confidence || 0)

  return (
    <div className="space-y-5">
      {/* ---- Headline card: risk + summary + score ---- */}
      <Card className={cfg.ring}>
        <CardHeader
          icon={HeaderIcon}
          title="Clinical Decision Report"
          subtitle="AI-assisted synthesis — verify with a clinician"
          action={
            <div className="text-right">
              <p className="text-xs text-muted">Risk level</p>
              <p className="text-lg font-bold" style={{ color: cfg.color }}>{cfg.label}</p>
            </div>
          }
        />

        {report.clinical_summary && (
          <p className="text-sm leading-relaxed text-foreground">{report.clinical_summary}</p>
        )}

        {/* Metric strip: risk score, confidence, red-flag tally */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl bg-surface-2 p-3 text-center">
            <p className="flex items-center justify-center gap-1 text-[11px] font-medium uppercase tracking-wide text-muted">
              <Gauge size={12} /> Risk score
            </p>
            <p className="mt-1 text-2xl font-bold" style={{ color: cfg.color }}>{score}</p>
          </div>
          <div className="rounded-xl bg-surface-2 p-3 text-center">
            <p className="flex items-center justify-center gap-1 text-[11px] font-medium uppercase tracking-wide text-muted">
              <Sparkles size={12} /> Confidence
            </p>
            <p className="mt-1 text-2xl font-bold text-foreground">{confidence}%</p>
          </div>
          <div className="rounded-xl bg-surface-2 p-3 text-center">
            <p className="flex items-center justify-center gap-1 text-[11px] font-medium uppercase tracking-wide text-muted">
              <Pill size={12} /> Medicines
            </p>
            <p className="mt-1 text-2xl font-bold text-foreground">{report.medicines?.length || 0}</p>
          </div>
          <div className="rounded-xl bg-surface-2 p-3 text-center">
            <p className="flex items-center justify-center gap-1 text-[11px] font-medium uppercase tracking-wide text-muted">
              <AlertOctagon size={12} /> Red flags
            </p>
            <p className="mt-1 text-2xl font-bold" style={{ color: redFlags.length ? 'var(--danger)' : 'var(--foreground)' }}>
              {redFlags.length}
            </p>
          </div>
        </div>

        {/* Severity tally badges */}
        {redFlags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {['critical', 'high', 'moderate', 'low'].map((s) =>
              report.risk_counts?.[s] ? (
                <Badge key={s} tone={risk(s).tone}>{report.risk_counts[s]} {risk(s).label}</Badge>
              ) : null,
            )}
          </div>
        )}
      </Card>

      {/* ---- Red-flag alerts (most urgent — surfaced right after the headline) ---- */}
      {redFlags.length > 0 && (
        <Card>
          <CardHeader icon={AlertOctagon} title="Red Flag Alerts" subtitle="Findings that warrant urgent attention" />
          <div className="space-y-3">
            {redFlags.map((f, i) => <RedFlagRow key={i} flag={f} />)}
          </div>
        </Card>
      )}

      {/* ---- Disease prediction ---- */}
      {diseases.length > 0 && (
        <Card>
          <CardHeader icon={Stethoscope} title="Disease Prediction" subtitle="Candidate conditions considered" />
          <div className="space-y-3">
            {diseases.map((d, i) => (
              <div key={i} className="rounded-xl bg-surface-2 p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-foreground">{titleCase(d.disease)}</p>
                  <div className="flex items-center gap-2">
                    {d.source === 'model' && (
                      <span className="text-sm font-semibold text-primary">{Math.round(d.confidence)}%</span>
                    )}
                    <Badge tone="neutral">{d.source}</Badge>
                  </div>
                </div>
                {d.explanation && <p className="mt-1.5 text-sm text-muted">{d.explanation}</p>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ---- Clinical findings grid ---- */}
      {(report.possible_risks?.length || report.contraindications?.length ||
        report.recommended_lab_tests?.length || report.recommended_next_steps?.length ||
        report.follow_up?.length || report.missing_information?.length) > 0 && (
        <Card>
          <CardHeader icon={Activity} title="Clinical Findings & Guidance" subtitle="Risks, work-up and next steps" />
          <div className="grid gap-4 md:grid-cols-2">
            <ListBlock icon={ListChecks} title="Recommended next steps" items={report.recommended_next_steps} />
            <ListBlock icon={FlaskConical} title="Recommended lab tests" items={report.recommended_lab_tests} />
            <ListBlock icon={AlertOctagon} title="Possible risks" items={report.possible_risks} tone="warning" accent="bg-warning" />
            <ListBlock icon={Ban} title="Contraindications" items={report.contraindications} tone="danger" accent="bg-danger" />
            <ListBlock icon={CalendarClock} title="Follow-up advice" items={report.follow_up} />
            <ListBlock icon={HelpCircle} title="Missing information" items={report.missing_information} tone="warning" accent="bg-warning" />
          </div>
        </Card>
      )}

      {/* ---- Embedded drug-interaction report (reuses the existing component) ---- */}
      {showInteractions && report.drug_interactions && (
        <DrugInteractionReport report={report.drug_interactions} />
      )}

      {/* ---- Knowledge-base context + provenance ---- */}
      {(report.rag_notes || report.sources?.length > 0) && (
        <Accordion
          title="Sources & knowledge-base context"
          subtitle="What informed this report"
          icon={BookOpen}
        >
          {report.rag_notes && (
            <p className="whitespace-pre-wrap text-sm text-muted">{report.rag_notes}</p>
          )}
          {report.sources?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {report.sources.map((s, i) => (
                <Badge key={i} tone="neutral">{s}</Badge>
              ))}
            </div>
          )}
        </Accordion>
      )}

      {/* ---- Warnings + disclaimer ---- */}
      {report.warnings?.length > 0 && (
        <div className="rounded-xl border border-warning/30 bg-warning/5 p-3 text-sm text-foreground">
          {report.warnings.map((w, i) => (
            <p key={i} className="flex gap-2"><span className="text-warning">•</span>{w}</p>
          ))}
        </div>
      )}
      {report.disclaimer && (
        <p className="px-2 text-center text-xs text-muted">{report.disclaimer}</p>
      )}
    </div>
  )
}
