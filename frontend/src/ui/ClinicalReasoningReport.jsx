import {
  User,
  ScanLine,
  Pill,
  Stethoscope,
  BookOpen,
  Workflow,
  GitCompareArrows,
  Gauge,
  ListTree,
  ClipboardCheck,
  CalendarClock,
  Library,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Lightbulb,
  Clock,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Badge from '@/ui/Badge'
import ReasoningPipeline from '@/ui/ReasoningPipeline'
import ConfidenceMeter from '@/ui/ConfidenceMeter'
import { titleCase, formatDate } from '@/lib/utils'

const RISK_TONE = { critical: 'danger', high: 'danger', moderate: 'warning', low: 'primary' }
const PRIORITY_TONE = RISK_TONE

function Section({ icon: Icon, title, subtitle, children, action }) {
  return (
    <Card className="animate-fade-up">
      <CardHeader icon={Icon} title={title} subtitle={subtitle} action={action} />
      {children}
    </Card>
  )
}

function Pillette({ children, tone = 'neutral' }) {
  return <Badge tone={tone}>{children}</Badge>
}

// ---- Diagnosis card (leading / considered / rejected) ----
function DiagnosisCard({ dx }) {
  const rejected = dx.status === 'rejected'
  const leading = dx.status === 'leading'
  return (
    <div
      className={`rounded-xl border p-3 ${
        leading ? 'border-primary/40 bg-primary-soft/40' : 'border-border bg-surface'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {leading ? (
            <CheckCircle2 size={16} className="text-primary" />
          ) : rejected ? (
            <XCircle size={16} className="text-danger" />
          ) : (
            <ListTree size={16} className="text-muted" />
          )}
          <span className="text-sm font-semibold text-foreground">{titleCase(dx.disease)}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs tabular-nums text-muted">{dx.confidence?.toFixed(0)}%</span>
          <Pillette tone={leading ? 'primary' : rejected ? 'danger' : 'neutral'}>
            {titleCase(dx.status)}
          </Pillette>
        </div>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div
          className="meter-fill h-full rounded-full bg-primary/70"
          style={{ width: `${Math.min(100, dx.confidence || 0)}%` }}
        />
      </div>
      {dx.supporting?.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          <span className="font-medium text-success">For:</span> {dx.supporting.join('; ')}
        </p>
      )}
      {dx.against?.length > 0 && (
        <p className="mt-1 text-xs text-muted">
          <span className="font-medium text-warning">Against:</span> {dx.against.join('; ')}
        </p>
      )}
      {rejected && dx.rejection_reason && (
        <p className="mt-1.5 rounded-lg bg-danger/10 px-2 py-1 text-xs text-danger">
          <span className="font-medium">Rejected:</span> {dx.rejection_reason}
        </p>
      )}
    </div>
  )
}

// ---- Evidence card ----
function EvidenceCard({ ev }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-foreground">{ev.title}</h4>
        {ev.relevance > 0 && (
          <Pillette tone="primary">{(ev.relevance * 100).toFixed(0)}% match</Pillette>
        )}
      </div>
      {ev.source && <p className="mt-0.5 text-[11px] text-muted">{ev.source}</p>}
      {ev.snippet && <p className="mt-1.5 text-xs leading-relaxed text-muted">{ev.snippet}</p>}
    </div>
  )
}

// ---- Rule chip ----
function RuleRow({ rule }) {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-border bg-surface p-2.5">
      <ShieldAlert size={15} className="mt-0.5 shrink-0 text-warning" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">{rule.name}</span>
          <Pillette tone={RISK_TONE[rule.severity] || 'neutral'}>{titleCase(rule.severity)}</Pillette>
        </div>
        <p className="text-xs text-muted">{rule.rationale}</p>
        {rule.triggered_by?.length > 0 && (
          <p className="mt-0.5 text-[11px] text-muted/70">Triggered by: {rule.triggered_by.join(', ')}</p>
        )}
      </div>
    </div>
  )
}

export default function ClinicalReasoningReport({ report }) {
  if (!report) return null
  const {
    patient_summary: ps,
    ocr_findings: ocr,
    medicine_analysis: meds,
    disease_prediction: dp,
    clinical_evidence: evidence = [],
    reasoning_chain: chain = [],
    drug_interaction_analysis: interactions,
    confidence_analysis: conf,
    alternative_diagnoses: alts = [],
    clinical_recommendations: recs = [],
    follow_up_suggestions: followUps = [],
    medical_references: refs = [],
    explanation = {},
    matched_rules: rules = [],
    risk_level,
    confidence,
  } = report

  return (
    <div className="space-y-5">
      {/* ---- Header banner ---- */}
      <Card className="animate-fade-up border-primary/30 bg-gradient-to-br from-primary-soft/60 to-surface">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Workflow size={22} />
            </span>
            <div>
              <h2 className="text-lg font-bold text-foreground">Clinical Reasoning Report</h2>
              <p className="text-xs text-muted">
                {report.created_at ? formatDate(report.created_at) : 'Just now'}
                {report.cached && ' · served from cache'}
                {report.duration_ms > 0 && ` · ${(report.duration_ms / 1000).toFixed(2)}s`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Pillette tone={RISK_TONE[risk_level] || 'primary'}>Risk: {titleCase(risk_level)}</Pillette>
            <Pillette tone="primary">Confidence: {confidence?.toFixed(0)}%</Pillette>
          </div>
        </div>
        {ps?.narrative && <p className="mt-3 text-sm text-foreground/90">{ps.narrative}</p>}
      </Card>

      {/* ---- 1. Patient Summary ---- */}
      <Section icon={User} title="Patient Summary">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ['Age', ps?.age ?? '—'],
            ['Gender', ps?.gender ? titleCase(ps.gender) : '—'],
            ['Symptoms', ps?.symptom_count ?? 0],
            ['Medicines', ps?.medicine_count ?? 0],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl bg-surface-2/60 p-3 text-center">
              <div className="text-lg font-bold text-foreground">{value}</div>
              <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
            </div>
          ))}
        </div>
      </Section>

      {/* ---- 2. OCR Findings ---- */}
      <Section icon={ScanLine} title="OCR Findings" subtitle={ocr?.note}>
        {ocr?.detected_medicines?.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {ocr.detected_medicines.map((m) => (
              <Pillette key={m} tone="neutral">{m}</Pillette>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No medicines detected from OCR.</p>
        )}
        {ocr?.diagnosis && (
          <p className="mt-2 text-sm text-muted">Diagnosis on prescription: <span className="font-medium text-foreground">{ocr.diagnosis}</span></p>
        )}
        {ocr?.raw_text && (
          <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-xl bg-surface-2/60 p-3 text-xs text-muted">
            {ocr.raw_text}
          </pre>
        )}
      </Section>

      {/* ---- 3. Medicine Analysis ---- */}
      <Section icon={Pill} title="Medicine Analysis">
        {meds?.insights?.length > 0 ? (
          <div className="space-y-2">
            {meds.insights.map((m) => (
              <div key={m.name} className="flex items-center gap-2 rounded-xl border border-border bg-surface p-2.5">
                {m.matched ? (
                  <CheckCircle2 size={15} className="shrink-0 text-success" />
                ) : (
                  <AlertTriangle size={15} className="shrink-0 text-warning" />
                )}
                <div className="min-w-0 flex-1">
                  <span className="text-sm font-medium text-foreground">{titleCase(m.name)}</span>
                  {m.resolved_name && m.resolved_name.toLowerCase() !== m.name.toLowerCase() && (
                    <span className="text-xs text-muted"> → {titleCase(m.resolved_name)}</span>
                  )}
                  <p className="text-xs text-muted">{m.influence}</p>
                </div>
                <Pillette tone={m.role === 'interacting' ? 'danger' : m.matched ? 'success' : 'warning'}>
                  {titleCase(m.role)}
                </Pillette>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No medicines to analyse.</p>
        )}
      </Section>

      {/* ---- 4. Disease Prediction (leading + why) ---- */}
      <Section icon={Stethoscope} title="Disease Prediction" subtitle={dp?.method}>
        {dp?.leading ? (
          <>
            <DiagnosisCard dx={dp.leading} />
            {explanation.why_disease && (
              <div className="mt-3 rounded-xl bg-primary-soft/40 p-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold text-primary">
                  <Lightbulb size={14} /> Why this diagnosis
                </p>
                <p className="mt-1 text-sm text-foreground/90">{explanation.why_disease}</p>
              </div>
            )}
            {explanation.contributing_symptoms?.length > 0 && (
              <div className="mt-3">
                <p className="mb-1.5 text-xs font-semibold text-muted">Contributing symptoms</p>
                <div className="space-y-1.5">
                  {explanation.contributing_symptoms.map((s) => (
                    <div key={s.symptom} className="flex items-center gap-2">
                      <span className="w-32 shrink-0 truncate text-xs text-foreground">{titleCase(s.symptom)}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                        <div
                          className="meter-fill h-full rounded-full bg-primary/70"
                          style={{ width: `${Math.round((s.weight || 0) * 100)}%` }}
                        />
                      </div>
                      <span className="w-24 shrink-0 text-right text-[11px] text-muted">{s.note}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="text-sm text-muted">No confident diagnosis could be derived from the inputs.</p>
        )}
      </Section>

      {/* ---- 5. Clinical Evidence ---- */}
      <Section icon={BookOpen} title="Clinical Evidence" subtitle="Retrieved from the RAG knowledge base">
        {evidence.length > 0 ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {evidence.map((ev) => (
              <EvidenceCard key={ev.id} ev={ev} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No knowledge-base evidence was retrieved for this case.</p>
        )}
      </Section>

      {/* ---- 6. Reasoning Chain (animated pipeline + timeline) ---- */}
      <Section icon={Workflow} title="Reasoning Chain" subtitle="Every step the platform took, in order">
        <ReasoningPipeline steps={chain} compact />
      </Section>

      {/* ---- 7. Drug Interaction Analysis ---- */}
      <Section icon={GitCompareArrows} title="Drug Interaction Analysis">
        {interactions?.interactions?.length > 0 ? (
          <div className="space-y-2">
            {interactions.interactions.map((it, idx) => (
              <div key={idx} className="rounded-xl border border-border bg-surface p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">
                    {(it.pair || it.medicines || []).map(titleCase).join(' + ')}
                  </span>
                  <Pillette tone={RISK_TONE[(it.severity || '').toLowerCase()] || 'neutral'}>
                    {titleCase(it.severity || 'note')}
                  </Pillette>
                </div>
                {(it.description || it.effect) && (
                  <p className="mt-1 text-xs text-muted">{it.description || it.effect}</p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No drug–drug interactions were found.</p>
        )}
      </Section>

      {/* ---- 8. Confidence Analysis ---- */}
      <Section icon={Gauge} title="Confidence Analysis" subtitle="How certain the platform is, and why">
        <ConfidenceMeter breakdown={conf?.breakdown} />
      </Section>

      {/* ---- 9. Alternative Diagnoses ---- */}
      <Section
        icon={ListTree}
        title="Alternative Diagnoses"
        subtitle="Considered and why the weaker ones were rejected"
      >
        {alts.length > 0 ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {alts.map((dx) => (
              <DiagnosisCard key={dx.disease} dx={dx} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No competing diagnoses were considered.</p>
        )}
      </Section>

      {/* ---- Clinical rules that fired ---- */}
      {rules.length > 0 && (
        <Section icon={ShieldAlert} title="Clinical Rules Matched" subtitle={`${rules.length} rule(s) fired`}>
          <div className="space-y-2">
            {rules.map((r) => (
              <RuleRow key={r.id} rule={r} />
            ))}
          </div>
        </Section>
      )}

      {/* ---- 10. Clinical Recommendations ---- */}
      <Section icon={ClipboardCheck} title="Clinical Recommendations">
        <div className="space-y-2">
          {recs.map((r, idx) => (
            <div key={idx} className="rounded-xl border border-border bg-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-foreground">{r.title}</span>
                <Pillette tone={PRIORITY_TONE[r.priority] || 'neutral'}>{titleCase(r.priority)}</Pillette>
              </div>
              {r.detail && <p className="mt-1 text-sm text-muted">{r.detail}</p>}
              {r.rationale && (
                <p className="mt-1 text-xs italic text-muted/80">Why: {r.rationale}</p>
              )}
            </div>
          ))}
        </div>
      </Section>

      {/* ---- 11. Follow-up Suggestions ---- */}
      <Section icon={CalendarClock} title="Follow-up Suggestions">
        <div className="space-y-2">
          {followUps.map((f, idx) => (
            <div key={idx} className="flex items-start gap-2.5 rounded-xl border border-border bg-surface p-2.5">
              <Clock size={15} className="mt-0.5 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-foreground">{f.action}</span>
                  {f.timeframe && <Pillette tone="primary">{f.timeframe}</Pillette>}
                </div>
                {f.reason && <p className="text-xs text-muted">{f.reason}</p>}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* ---- 12. Medical References ---- */}
      <Section icon={Library} title="Medical References">
        {refs.length > 0 ? (
          <ul className="space-y-2">
            {refs.map((ref, idx) => (
              <li key={idx} className="flex items-start gap-2 text-sm">
                <span className="mt-0.5 text-xs tabular-nums text-muted">[{idx + 1}]</span>
                <div>
                  <span className="font-medium text-foreground">{ref.label}</span>
                  {ref.source && <span className="text-muted"> — {ref.source}</span>}
                  {ref.detail && <p className="text-xs text-muted">{ref.detail}</p>}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">No references were surfaced for this case.</p>
        )}
      </Section>

      {report.disclaimer && (
        <p className="rounded-xl border border-dashed border-border bg-surface/50 p-3 text-xs leading-relaxed text-muted">
          {report.disclaimer}
        </p>
      )}
    </div>
  )
}
