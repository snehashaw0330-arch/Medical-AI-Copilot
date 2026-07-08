import { cn, confidenceColor, titleCase } from '@/lib/utils'

/**
 * Radial confidence meter with a weighted component breakdown.
 *
 * @param {object} breakdown - { overall, level, components:[{name,weight,score,contribution,note}],
 *                               missing_information:[], rationale }
 */
export default function ConfidenceMeter({ breakdown }) {
  if (!breakdown) return null
  const overall = Math.max(0, Math.min(100, breakdown.overall || 0))
  const color = confidenceColor(overall)

  // Semicircle gauge geometry.
  const R = 52
  const CIRC = Math.PI * R // half circumference
  const dash = (overall / 100) * CIRC

  return (
    <div className="grid gap-6 sm:grid-cols-[auto_1fr] sm:items-center">
      {/* Gauge */}
      <div className="mx-auto flex flex-col items-center">
        <svg width="140" height="86" viewBox="0 0 140 86" className="overflow-visible">
          <path
            d="M 14 78 A 56 56 0 0 1 126 78"
            fill="none"
            stroke="var(--surface-2)"
            strokeWidth="12"
            strokeLinecap="round"
          />
          <path
            d="M 14 78 A 56 56 0 0 1 126 78"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${CIRC}`}
            style={{ transition: 'stroke-dasharray 0.9s ease-out' }}
          />
        </svg>
        <div className="-mt-8 text-center">
          <div className="text-3xl font-bold tabular-nums" style={{ color }}>
            {overall.toFixed(0)}
            <span className="text-lg">%</span>
          </div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted">
            {titleCase(breakdown.level || '')}
          </div>
        </div>
      </div>

      {/* Component breakdown */}
      <div className="space-y-2.5">
        {(breakdown.components || []).map((c) => {
          const score = Math.max(0, Math.min(100, c.score || 0))
          return (
            <div key={c.name}>
              <div className="flex items-baseline justify-between gap-2 text-xs">
                <span className="font-medium text-foreground">{titleCase(c.name)}</span>
                <span className="tabular-nums text-muted">
                  {score.toFixed(0)}
                  <span className="text-muted/60"> × {(c.weight * 100).toFixed(0)}% = </span>
                  <span className="font-semibold text-foreground">+{c.contribution?.toFixed(1)}</span>
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                <div
                  className="meter-fill h-full rounded-full"
                  style={{ width: `${score}%`, backgroundColor: confidenceColor(score) }}
                  title={c.note}
                />
              </div>
            </div>
          )
        })}
      </div>

      {/* Rationale + missing info span full width */}
      {(breakdown.rationale || (breakdown.missing_information || []).length > 0) && (
        <div className="sm:col-span-2">
          {breakdown.rationale && (
            <p className="rounded-xl bg-surface-2/60 p-3 text-xs leading-relaxed text-muted">
              {breakdown.rationale}
            </p>
          )}
          {(breakdown.missing_information || []).length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-medium text-muted">Would improve confidence:</span>
              {breakdown.missing_information.map((m) => (
                <span
                  key={m}
                  className={cn(
                    'inline-flex items-center rounded-full border border-dashed border-border',
                    'px-2 py-0.5 text-[11px] text-muted',
                  )}
                >
                  {m}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
