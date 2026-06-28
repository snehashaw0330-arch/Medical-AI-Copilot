import {
  ShieldAlert,
  ShieldCheck,
  Pill,
  AlertTriangle,
  Lightbulb,
  Utensils,
  Wine,
  Baby,
  HeartPulse,
  Droplets,
  Ban,
  Users,
  BookOpen,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Badge from '@/ui/Badge'
import Accordion from '@/ui/Accordion'
import { titleCase } from '@/lib/utils'

/**
 * Drug Interaction Report card (Requirement 8).
 *
 * Renders the backend `InteractionReport` shape: overall risk, color-coded
 * severity badges, the medicines involved, each pairwise interaction, the
 * aggregated recommendations, the per-drug warnings (food / alcohol / pregnancy
 * / breastfeeding / kidney / liver / age / contraindications), and any extra
 * context retrieved from the RAG knowledge base.
 *
 * Pure presentation — it takes a `report` object and renders. It is reused by
 * the OCR results page and can be dropped into a history detail view unchanged.
 */

// Severity → UI treatment. Mirrors backend utils.SEVERITY_TONE.
const SEVERITY = {
  critical: { label: 'Critical', tone: 'danger', color: 'var(--danger)', ring: 'border-danger/40 bg-danger/5' },
  high: { label: 'High', tone: 'danger', color: 'var(--danger)', ring: 'border-danger/30 bg-danger/5' },
  moderate: { label: 'Moderate', tone: 'warning', color: 'var(--warning)', ring: 'border-warning/30 bg-warning/5' },
  low: { label: 'Low', tone: 'primary', color: 'var(--primary)', ring: 'border-primary/30 bg-primary/5' },
  none: { label: 'No known risk', tone: 'success', color: 'var(--success)', ring: 'border-success/30 bg-success/5' },
}

const sev = (s) => SEVERITY[s] || SEVERITY.none

// Per-drug warning categories, in display order, with an icon each.
const WARNING_CATEGORIES = [
  { key: 'contraindications', label: 'Contraindications', icon: Ban },
  { key: 'food', label: 'Food', icon: Utensils },
  { key: 'alcohol', label: 'Alcohol', icon: Wine },
  { key: 'pregnancy', label: 'Pregnancy', icon: Baby },
  { key: 'breastfeeding', label: 'Breastfeeding', icon: Baby },
  { key: 'kidney', label: 'Kidney', icon: Droplets },
  { key: 'liver', label: 'Liver', icon: HeartPulse },
  { key: 'age_restrictions', label: 'Age restrictions', icon: Users },
]

function SeverityBadge({ severity }) {
  const cfg = sev(severity)
  return <Badge tone={cfg.tone}>{cfg.label}</Badge>
}

function InteractionRow({ interaction }) {
  const cfg = sev(interaction.severity)
  return (
    <div className={`rounded-xl border p-4 ${cfg.ring}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold text-foreground">
          <AlertTriangle size={16} style={{ color: cfg.color }} />
          {(interaction.medicines || []).map((m) => titleCase(m)).join(' + ')}
        </p>
        <SeverityBadge severity={interaction.severity} />
      </div>
      {interaction.clinical_risk && (
        <p className="mt-2 text-sm font-medium" style={{ color: cfg.color }}>
          {interaction.clinical_risk}
        </p>
      )}
      {interaction.explanation && (
        <p className="mt-2 text-sm text-muted">{interaction.explanation}</p>
      )}
      {interaction.recommendation && (
        <p className="mt-2 text-sm text-foreground">
          <span className="font-semibold">Recommendation: </span>
          {interaction.recommendation}
        </p>
      )}
      {interaction.clinical_notes && (
        <p className="mt-1 text-xs text-muted">
          <span className="font-medium">Clinical note: </span>
          {interaction.clinical_notes}
        </p>
      )}
    </div>
  )
}

function MedicineWarnings({ w }) {
  const present = WARNING_CATEGORIES.filter((c) => (w[c.key] || []).length > 0)
  if (!w.matched) {
    return (
      <p className="text-sm text-muted">
        <span className="font-medium text-foreground">{titleCase(w.medicine)}</span> — not found in
        the interaction knowledge base, so no warnings are available. Verify manually.
      </p>
    )
  }
  if (!present.length) return null
  return (
    <div>
      <p className="mb-2 flex items-center gap-2 font-semibold text-foreground">
        <Pill size={15} className="text-primary" /> {titleCase(w.medicine)}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {present.map(({ key, label, icon: Icon }) => (
          <div key={key} className="rounded-xl bg-surface-2 p-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
              <Icon size={13} className="text-primary" /> {label}
            </p>
            <ul className="mt-1.5 space-y-1">
              {w[key].map((item, i) => (
                <li key={i} className="flex gap-2 text-sm text-foreground">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function DrugInteractionReport({ report }) {
  if (!report) return null
  const cfg = sev(report.overall_risk)
  const interactions = report.interactions || []
  const warnings = report.warnings || []
  const recommendations = report.recommendations || []
  const hasWarnings = warnings.some((w) => !w.matched || WARNING_CATEGORIES.some((c) => (w[c.key] || []).length))
  const Icon = report.overall_risk === 'none' ? ShieldCheck : ShieldAlert

  return (
    <Card className={cfg.ring}>
      <CardHeader
        icon={Icon}
        title="Drug Interaction Report"
        subtitle="Automated analysis of the detected medicines"
        action={
          <div className="text-right">
            <p className="text-xs text-muted">Risk level</p>
            <p className="text-lg font-bold" style={{ color: cfg.color }}>
              {cfg.label}
            </p>
          </div>
        }
      />

      {/* Summary + severity tally */}
      <p className="text-sm text-foreground">{report.summary}</p>
      {interactions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {['critical', 'high', 'moderate', 'low'].map((s) =>
            report.risk_counts?.[s] ? (
              <Badge key={s} tone={sev(s).tone}>
                {report.risk_counts[s]} {sev(s).label}
              </Badge>
            ) : null,
          )}
        </div>
      )}

      {/* Medicines involved */}
      <div className="mt-4">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Medicines involved</p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {(report.medicines || []).map((m, i) => {
            const unmatched = (report.unmatched_medicines || []).includes(m)
            return (
              <Badge key={i} tone={unmatched ? 'neutral' : 'primary'}>
                {titleCase(m)}
                {unmatched ? ' · unknown' : ''}
              </Badge>
            )
          })}
        </div>
      </div>

      {/* Pairwise interactions */}
      {interactions.length > 0 && (
        <div className="mt-5 space-y-3">
          {interactions.map((it, i) => (
            <InteractionRow key={i} interaction={it} />
          ))}
        </div>
      )}

      {/* Aggregated recommendations */}
      {recommendations.length > 0 && (
        <div className="mt-5 rounded-xl bg-surface-2 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Lightbulb size={15} className="text-primary" /> Recommendations
          </p>
          <ul className="mt-2 space-y-1.5">
            {recommendations.map((r, i) => (
              <li key={i} className="flex gap-2 text-sm text-foreground">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Per-drug warnings (collapsible to keep the card compact) */}
      {hasWarnings && (
        <div className="mt-5">
          <Accordion
            title="Medicine-specific warnings"
            subtitle="Food, alcohol, pregnancy, breastfeeding, kidney, liver & age guidance"
            icon={AlertTriangle}
          >
            <div className="space-y-5">
              {warnings.map((w, i) => (
                <MedicineWarnings key={i} w={w} />
              ))}
            </div>
          </Accordion>
        </div>
      )}

      {/* RAG knowledge-base context */}
      {report.rag_notes && (
        <div className="mt-5">
          <Accordion
            title="From the knowledge base"
            subtitle="Additional context retrieved by the RAG module"
            icon={BookOpen}
          >
            <p className="whitespace-pre-wrap text-sm text-muted">{report.rag_notes}</p>
            {report.rag_sources?.length > 0 && (
              <p className="mt-2 text-xs text-muted">
                <span className="font-medium text-foreground">Sources: </span>
                {report.rag_sources.join(', ')}
              </p>
            )}
          </Accordion>
        </div>
      )}

      {report.disclaimer && (
        <p className="mt-4 text-xs text-muted">{report.disclaimer}</p>
      )}
    </Card>
  )
}
