import {
  ScanLine,
  Pill,
  ShieldCheck,
  GitCompareArrows,
  Stethoscope,
  BookOpen,
  Scale,
  ListTree,
  Gauge,
  ClipboardCheck,
  Check,
  X,
  Minus,
  Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// Stable icon per pipeline step key (mirrors backend _PIPELINE order).
const STEP_ICONS = {
  ocr: ScanLine,
  medicine_detection: Pill,
  medicine_validation: ShieldCheck,
  drug_interactions: GitCompareArrows,
  disease_prediction: Stethoscope,
  evidence_retrieval: BookOpen,
  clinical_rules: Scale,
  differential: ListTree,
  confidence: Gauge,
  recommendation: ClipboardCheck,
}

const STATUS_STYLES = {
  complete: {
    ring: 'border-success bg-success/10 text-success',
    dot: 'bg-success',
    label: 'Done',
    tone: 'text-success',
  },
  running: {
    ring: 'border-primary bg-primary-soft text-primary reasoning-pulse',
    dot: 'bg-primary',
    label: 'Running',
    tone: 'text-primary',
  },
  pending: {
    ring: 'border-border bg-surface-2 text-muted',
    dot: 'bg-muted/40',
    label: 'Pending',
    tone: 'text-muted',
  },
  skipped: {
    ring: 'border-border bg-surface-2 text-muted',
    dot: 'bg-muted/40',
    label: 'Skipped',
    tone: 'text-muted',
  },
  failed: {
    ring: 'border-danger bg-danger/10 text-danger',
    dot: 'bg-danger',
    label: 'Failed',
    tone: 'text-danger',
  },
}

function StatusGlyph({ status }) {
  if (status === 'complete') return <Check size={16} />
  if (status === 'running') return <Loader2 size={16} className="animate-spin" />
  if (status === 'failed') return <X size={16} />
  if (status === 'skipped') return <Minus size={16} />
  return null
}

/**
 * Animated vertical reasoning pipeline.
 *
 * @param {Array} steps    - [{ order, key, name, status, title, summary, duration_ms }]
 * @param {string} activeKey - optional key to force-highlight (live run)
 * @param {boolean} compact  - denser layout (used inside the report)
 */
export default function ReasoningPipeline({ steps = [], activeKey = null, compact = false }) {
  return (
    <ol className="relative">
      {steps.map((step, i) => {
        const status = activeKey === step.key ? 'running' : step.status || 'pending'
        const style = STATUS_STYLES[status] || STATUS_STYLES.pending
        const Icon = STEP_ICONS[step.key] || ListTree
        const isLast = i === steps.length - 1
        const nextDone = steps[i + 1] && ['complete', 'skipped'].includes(steps[i + 1].status)

        return (
          <li
            key={step.key || i}
            className="reasoning-node-in relative flex gap-4 pb-1"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            {/* Connector + node */}
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  'relative z-10 grid place-items-center rounded-full border-2 transition-colors',
                  compact ? 'h-9 w-9' : 'h-11 w-11',
                  style.ring,
                )}
              >
                <Icon size={compact ? 15 : 18} />
              </span>
              {!isLast && (
                <span className="relative my-0.5 w-0.5 flex-1 overflow-hidden rounded-full bg-border">
                  {status === 'running' && (
                    <span className="absolute inset-0 reasoning-flow" />
                  )}
                  {(status === 'complete' && nextDone) && (
                    <span className="absolute inset-0 bg-success/60" />
                  )}
                </span>
              )}
            </div>

            {/* Content */}
            <div className={cn('min-w-0 flex-1', compact ? 'pb-4' : 'pb-6')}>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold tabular-nums text-muted">
                  {String(step.order || i + 1).padStart(2, '0')}
                </span>
                <h4 className="truncate text-sm font-semibold text-foreground">{step.name}</h4>
                <span
                  className={cn(
                    'ml-auto inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
                    style.ring.replace('reasoning-pulse', ''),
                  )}
                >
                  <StatusGlyph status={status} />
                  {style.label}
                </span>
              </div>
              {step.title && (
                <p className={cn('mt-0.5 text-sm font-medium', style.tone)}>{step.title}</p>
              )}
              {step.summary && (
                <p className="mt-0.5 text-xs leading-relaxed text-muted">{step.summary}</p>
              )}
              {step.duration_ms > 0 && (
                <p className="mt-1 text-[10px] tabular-nums text-muted/70">
                  {step.duration_ms >= 1000
                    ? `${(step.duration_ms / 1000).toFixed(2)}s`
                    : `${Math.round(step.duration_ms)}ms`}
                </p>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
