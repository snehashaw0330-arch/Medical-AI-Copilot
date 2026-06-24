import {
  Gauge,
  Sun,
  Contrast,
  Focus,
  Sparkles,
  Maximize,
  RotateCw,
  Lightbulb,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import { confidenceColor, titleCase } from '@/lib/utils'

/**
 * Quality Report card. Renders the response from POST /ocr/image-quality:
 * an overall 0..100 score, per-metric sub-score bars, raw measurements, and
 * actionable recommendations. Purely presentational.
 */

const round = (v, d = 0) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return d ? n.toFixed(d) : Math.round(n)
}

// Sub-scores returned by the backend, with display labels + icons.
const SUBSCORE_META = [
  ['sharpness', 'Sharpness', Focus],
  ['brightness', 'Brightness', Sun],
  ['contrast', 'Contrast', Contrast],
  ['noise', 'Noise', Sparkles],
  ['resolution', 'Resolution', Maximize],
  ['geometry', 'Orientation', RotateCw],
]

function ScoreBar({ label, icon: Icon, value }) {
  const v = Math.round(Number(value) || 0)
  const color = confidenceColor(v)
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 font-medium text-foreground">
          <Icon size={13} className="text-muted" /> {label}
        </span>
        <span className="font-semibold" style={{ color }}>{v}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full transition-all" style={{ width: `${v}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <div className="rounded-xl bg-surface-2 p-3 text-center">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
    </div>
  )
}

export default function QualityReport({ report }) {
  if (!report) return null
  const { overall_score: score, rating, passed, threshold, metrics = {}, subscores = {}, recommendations = [] } = report
  const pct = Math.round(Number(score) || 0)
  const color = confidenceColor(pct)
  const isGoodOnly = recommendations.length === 1 && /looks good/i.test(recommendations[0])

  return (
    <Card className={passed ? '' : 'border-warning/40 bg-warning/5'}>
      <CardHeader
        icon={Gauge}
        title="Image Quality Report"
        subtitle="Analyzed with OpenCV before OCR"
        action={
          <div className="text-right">
            <p className="text-xs text-muted">Overall</p>
            <p className="text-2xl font-bold leading-none" style={{ color }}>{pct}%</p>
            <p className="text-[11px] font-medium" style={{ color }}>{titleCase(rating || '')}</p>
          </div>
        }
      />

      {/* Pass / warn banner */}
      {passed ? (
        <div className="mb-4 flex items-start gap-2 rounded-xl bg-success/10 p-3 text-sm text-foreground">
          <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-success" />
          <span>Quality is sufficient for OCR.</span>
        </div>
      ) : (
        <div className="mb-4 flex items-start gap-2 rounded-xl bg-warning/10 p-3 text-sm text-foreground">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
          <span>
            <span className="font-semibold">Low quality ({pct}%, below {round(threshold)}%).</span>{' '}
            OCR accuracy may suffer — consider recapturing before continuing.
          </span>
        </div>
      )}

      {/* Sub-score bars */}
      <div className="grid gap-3 sm:grid-cols-2">
        {SUBSCORE_META.filter(([k]) => subscores[k] != null).map(([k, label, Icon]) => (
          <ScoreBar key={k} label={label} icon={Icon} value={subscores[k]} />
        ))}
      </div>

      {/* Raw measurements */}
      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric label="Resolution" value={`${round(metrics.width)}×${round(metrics.height)}`} />
        <Metric label="Megapixels" value={`${round(metrics.megapixels, 2)} MP`} />
        <Metric label="Blur (Laplacian)" value={round(metrics.blur_score)} />
        <Metric label="Brightness" value={round(metrics.brightness)} />
        <Metric label="Contrast" value={round(metrics.contrast)} />
        <Metric label="Sharpness" value={round(metrics.sharpness)} />
        <Metric label="Noise σ" value={round(metrics.noise_level, 2)} />
        <Metric label="Rotation / Skew" value={`${round(metrics.rotation_angle, 1)}° / ${round(metrics.skew_angle, 1)}°`} />
      </div>

      {/* Recommendations */}
      {recommendations.length > 0 && !isGoodOnly && (
        <div className="mt-5">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            <Lightbulb size={15} className="text-primary" /> Recommendations
          </p>
          <ul className="mt-2 space-y-1.5">
            {recommendations.map((r, i) => (
              <li key={i} className="flex gap-2 text-sm text-muted">
                <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}
