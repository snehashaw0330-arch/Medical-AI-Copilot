import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  AlertTriangle,
  ClipboardList,
  Copy,
  FileWarning,
  Wrench,
  CheckCircle2,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Badge from '@/ui/Badge'
import { titleCase } from '@/lib/utils'

/**
 * Prescription Validation Report card (Requirement 7).
 *
 * Renders the backend `ValidationReport` shape: a 0..100 validation score, the
 * three-level risk grade, the missing dosing information, duplicate medicines /
 * active ingredients, the prescription warnings (unsafe abbreviations, suspicious
 * or low-confidence names, composite errors) and the suggested corrections — each
 * with the plain-language reason it was flagged.
 *
 * Pure presentation — it takes a `report` object and renders. It is reused by the
 * OCR results page and can be dropped into a history detail view unchanged.
 */

// Risk grade → UI treatment.
const RISK = {
  safe: { label: 'Safe', tone: 'success', color: 'var(--success)', ring: 'border-success/30 bg-success/5', icon: ShieldCheck },
  needs_review: { label: 'Needs Review', tone: 'warning', color: 'var(--warning)', ring: 'border-warning/30 bg-warning/5', icon: ShieldAlert },
  high_risk: { label: 'High Risk', tone: 'danger', color: 'var(--danger)', ring: 'border-danger/30 bg-danger/5', icon: ShieldX },
}
const risk = (r) => RISK[r] || RISK.safe

// Per-issue severity → badge tone.
const SEV_TONE = { high: 'danger', medium: 'warning', low: 'neutral' }
const sevTone = (s) => SEV_TONE[s] || 'neutral'

function IssueRow({ issue }) {
  return (
    <div className="rounded-xl bg-surface-2 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <AlertTriangle size={15} style={{ color: `var(--${sevTone(issue.severity) === 'neutral' ? 'muted' : sevTone(issue.severity)})` }} />
          {issue.title}
          {issue.medicine && <span className="text-muted">· {titleCase(issue.medicine)}</span>}
        </p>
        <Badge tone={sevTone(issue.severity)}>{titleCase(issue.severity)}</Badge>
      </div>
      <p className="mt-1.5 text-sm text-muted">{issue.detail}</p>
      {issue.recommendation && (
        <p className="mt-1 text-sm text-foreground">
          <span className="font-semibold">Fix: </span>{issue.recommendation}
        </p>
      )}
      {issue.evidence && (
        <p className="mt-1 text-xs text-muted">
          <span className="font-medium">Detected: </span>
          <code className="rounded bg-background px-1 py-0.5">{issue.evidence}</code>
        </p>
      )}
    </div>
  )
}

function Section({ icon: Icon, title, count, children }) {
  return (
    <div className="mt-5">
      <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon size={15} className="text-primary" /> {title}
        {typeof count === 'number' && (
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-muted">{count}</span>
        )}
      </p>
      {children}
    </div>
  )
}

export default function PrescriptionValidationReport({ report }) {
  if (!report) return null
  const cfg = risk(report.risk_level)
  const Icon = cfg.icon
  const score = Math.round(report.validation_score ?? 0)

  const missing = report.missing_information || []
  const duplicates = report.duplicate_medicines || []
  const warnings = report.warnings || []
  const corrections = report.suggested_corrections || []
  const clean = !missing.length && !duplicates.length && !warnings.length

  return (
    <Card className={cfg.ring}>
      <CardHeader
        icon={Icon}
        title="Prescription Validation"
        subtitle="Automated safety check of the extracted prescription"
        action={
          <div className="text-right">
            <p className="text-xs text-muted">Validation score</p>
            <p className="text-2xl font-bold leading-tight" style={{ color: cfg.color }}>{score}%</p>
          </div>
        }
      />

      {/* Risk level + severity tally */}
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={cfg.tone}>{cfg.label}</Badge>
        {['high', 'medium', 'low'].map((s) =>
          report.issue_counts?.[s] ? (
            <Badge key={s} tone={sevTone(s)}>
              {report.issue_counts[s]} {titleCase(s)}
            </Badge>
          ) : null,
        )}
      </div>
      {report.summary && <p className="mt-3 text-sm text-foreground">{report.summary}</p>}

      {clean && (
        <div className="mt-4 flex items-start gap-2 rounded-xl bg-success/10 p-3 text-sm text-foreground">
          <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-success" />
          <span>No safety issues were detected. Always confirm against the original prescription before dispensing.</span>
        </div>
      )}

      {/* Missing information */}
      {missing.length > 0 && (
        <Section icon={ClipboardList} title="Missing Information" count={missing.length}>
          <div className="space-y-2">
            {missing.map((i, idx) => <IssueRow key={idx} issue={i} />)}
          </div>
        </Section>
      )}

      {/* Duplicate medicines / active ingredients */}
      {duplicates.length > 0 && (
        <Section icon={Copy} title="Duplicate Medicines" count={duplicates.length}>
          <div className="space-y-2">
            {duplicates.map((g, idx) => (
              <div key={idx} className="rounded-xl bg-surface-2 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-foreground">
                    {g.kind === 'active_ingredient' ? 'Same active ingredient' : 'Repeated medicine'}
                    <span className="ml-1.5 font-normal text-muted">· {titleCase(g.value)}</span>
                  </p>
                  <Badge tone="danger">High</Badge>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(g.medicines || []).map((m, i) => (
                    <Badge key={i} tone="primary">{titleCase(m)}</Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Prescription warnings */}
      {warnings.length > 0 && (
        <Section icon={FileWarning} title="Prescription Warnings" count={warnings.length}>
          <div className="space-y-2">
            {warnings.map((i, idx) => <IssueRow key={idx} issue={i} />)}
          </div>
        </Section>
      )}

      {/* Suggested corrections */}
      {corrections.length > 0 && (
        <div className="mt-5 rounded-xl bg-surface-2 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Wrench size={15} className="text-primary" /> Suggested Corrections
          </p>
          <ul className="mt-2 space-y-1.5">
            {corrections.map((c, i) => (
              <li key={i} className="flex gap-2 text-sm text-foreground">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.disclaimer && <p className="mt-4 text-xs text-muted">{report.disclaimer}</p>}
    </Card>
  )
}
