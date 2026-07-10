import {
  ShieldCheck,
  ShieldAlert,
  Gauge,
  BookOpen,
  Quote,
  TriangleAlert,
  CheckCircle2,
  CircleHelp,
  XCircle,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Badge from '@/ui/Badge'
import ConfidenceMeter from '@/ui/ConfidenceMeter'
import { titleCase } from '@/lib/utils'

// Hallucination-risk → badge tone + label.
const RISK_TONE = { very_low: 'success', low: 'success', medium: 'warning', high: 'danger', critical: 'danger' }
// Claim support → visual treatment.
const SUPPORT_STYLE = {
  supported: { tone: 'success', ring: 'border-success/40 bg-success/10', icon: CheckCircle2, label: 'Supported' },
  weak: { tone: 'warning', ring: 'border-warning/40 bg-warning/10', icon: CircleHelp, label: 'Weak' },
  unsupported: { tone: 'danger', ring: 'border-danger/50 bg-danger/10', icon: XCircle, label: 'Unsupported' },
  contradicted: { tone: 'danger', ring: 'border-danger/60 bg-danger/15', icon: TriangleAlert, label: 'Contradicted' },
}

function MetricTile({ label, value, suffix = '', tone = 'foreground' }) {
  const color = { success: 'text-success', warning: 'text-warning', danger: 'text-danger', foreground: 'text-foreground' }[tone]
  return (
    <div className="rounded-xl bg-surface-2/60 p-3 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value}<span className="text-sm">{suffix}</span></div>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
    </div>
  )
}

/**
 * Evidence Verification panel — renders a full VerificationResult.
 * Embeddable in any page (e.g. next to an AI Chat answer).
 */
export default function EvidenceVerificationPanel({ result, compact = false }) {
  if (!result) return null
  const m = result.metrics || {}
  const risk = m.hallucination_risk || 'medium'
  const coverageTone = m.evidence_coverage >= 70 ? 'success' : m.evidence_coverage >= 40 ? 'warning' : 'danger'

  return (
    <div className="space-y-4">
      {/* Header + risk badge + verdict */}
      <Card className="animate-fade-up">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className={`grid h-11 w-11 place-items-center rounded-xl ${RISK_TONE[risk] === 'success' ? 'bg-success/15 text-success' : RISK_TONE[risk] === 'warning' ? 'bg-warning/15 text-warning' : 'bg-danger/15 text-danger'}`}>
              {RISK_TONE[risk] === 'success' ? <ShieldCheck size={22} /> : <ShieldAlert size={22} />}
            </span>
            <div>
              <h3 className="font-semibold text-foreground">Evidence Verification</h3>
              <p className="text-xs text-muted">
                {result.method === 'semantic' ? 'Semantic' : 'Lexical'} check
                {result.generated && ' · RAG-generated answer'}
                {result.cached && ' · cached'}
              </p>
            </div>
          </div>
          <Badge tone={RISK_TONE[risk]}>
            {RISK_TONE[risk] === 'success' ? <ShieldCheck size={13} /> : <ShieldAlert size={13} />}
            Hallucination risk: {titleCase(risk)}
          </Badge>
        </div>
        {result.verdict && <p className="mt-3 text-sm text-foreground/90">{result.verdict}</p>}

        {/* Metric tiles */}
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetricTile label="Evidence Coverage" value={Math.round(m.evidence_coverage || 0)} suffix="%" tone={coverageTone} />
          <MetricTile label="Confidence" value={Math.round(m.confidence || 0)} suffix="%" />
          <MetricTile label="Citation Strength" value={Math.round(m.citation_strength || 0)} suffix="%" />
          <MetricTile label="Risk Score" value={Math.round(m.hallucination_risk_score || 0)} tone={RISK_TONE[risk]} />
        </div>
      </Card>

      {/* Verified response with per-claim highlighting */}
      {result.claims?.length > 0 && (
        <Card className="animate-fade-up">
          <CardHeader icon={ShieldCheck} title="Verified Response" subtitle="Each claim is checked against the evidence; unsupported claims are flagged in red" />
          <div className="space-y-2">
            {result.claims.map((c) => {
              const st = SUPPORT_STYLE[c.support] || SUPPORT_STYLE.unsupported
              const Icon = st.icon
              return (
                <div key={c.id} className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${st.ring}`}>
                  <Icon size={15} className={`mt-0.5 shrink-0 ${st.tone === 'success' ? 'text-success' : st.tone === 'warning' ? 'text-warning' : 'text-danger'}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-foreground">{c.text}</p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2">
                      <Badge tone={st.tone}>{st.label}</Badge>
                      <span className="text-[11px] text-muted">match {Math.round((c.similarity || 0) * 100)}%{c.best_source ? ` · ${c.best_source}` : ''}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Unsupported statements (highlighted red) */}
      {(result.unsupported_claims?.length > 0 || result.contradictions?.length > 0) && (
        <Card className="animate-fade-up border-danger/40">
          <CardHeader icon={TriangleAlert} title="Unsupported Statements" subtitle="Claims with no supporting evidence (or that contradict it)" />
          <div className="space-y-2">
            {result.contradictions?.map((c) => (
              <div key={c.claim_id} className="rounded-lg border border-danger/50 bg-danger/15 px-3 py-2">
                <p className="text-sm font-medium text-danger">⚠ Contradicted: {c.claim_text}</p>
                {c.evidence_snippet && <p className="mt-0.5 text-xs text-muted">Evidence: “{c.evidence_snippet}”{c.source ? ` — ${c.source}` : ''}</p>}
              </div>
            ))}
            {result.unsupported_claims?.map((text, i) => (
              <div key={i} className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2">
                <p className="text-sm text-danger">{text}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Confidence meter */}
      {result.confidence_breakdown?.components?.length > 0 && (
        <Card className="animate-fade-up">
          <CardHeader icon={Gauge} title="Confidence" subtitle="How the confidence score is composed" />
          <ConfidenceMeter breakdown={result.confidence_breakdown} />
        </Card>
      )}

      {/* Supporting citations */}
      {result.citations?.length > 0 && (
        <Card className="animate-fade-up">
          <CardHeader icon={Quote} title="Supporting Citations" subtitle={`${result.citations.length} claim(s) backed by evidence`} />
          <div className="space-y-2">
            {result.citations.map((c, i) => (
              <div key={i} className="rounded-xl border border-border bg-surface p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm text-foreground">{c.claim_text}</p>
                  <Badge tone="success">{Math.round(c.strength)}%</Badge>
                </div>
                {c.snippet && <p className="mt-1 border-l-2 border-success/40 pl-2 text-xs text-muted">“{c.snippet}”</p>}
                {c.source && <p className="mt-1 text-[11px] text-muted">— {c.source}</p>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Retrieved documents */}
      {result.evidence?.length > 0 && !compact && (
        <Card className="animate-fade-up">
          <CardHeader icon={BookOpen} title="Retrieved Documents" subtitle={`${result.evidence.length} document(s) used for verification`} />
          <div className="grid gap-2 sm:grid-cols-2">
            {result.evidence.map((e) => (
              <div key={e.id} className="rounded-xl border border-border bg-surface p-3">
                <div className="flex items-start justify-between gap-2">
                  <h4 className="text-sm font-semibold text-foreground">{e.title}</h4>
                  <Badge tone="primary">{Math.round((e.relevance || 0) * 100)}%</Badge>
                </div>
                {e.source && <p className="mt-0.5 text-[11px] text-muted">{e.source}</p>}
                {e.snippet && <p className="mt-1.5 text-xs text-muted">{e.snippet}</p>}
                {e.supports_claims?.length > 0 && (
                  <p className="mt-1 text-[11px] text-success">Supports {e.supports_claims.length} claim(s)</p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
