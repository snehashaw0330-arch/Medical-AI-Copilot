import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Sparkles,
  Pill,
  Activity,
  Replace,
  Layers,
  Beaker,
  AlertTriangle,
  ShieldCheck,
  BookOpen,
  Info,
  History,
  FileText,
  Baby,
  Utensils,
  Archive,
  Stethoscope,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import ConfidenceBar from '@/ui/ConfidenceBar'
import TagInput from '@/ui/TagInput'
import EmptyState from '@/ui/EmptyState'
import { CardSkeleton } from '@/ui/Skeleton'
import {
  recommendMedicines,
  getMedicineRecommendations,
  getMedicineRecommendation,
} from '@/lib/api'
import { errorMessage, titleCase, formatDate, confidenceColor } from '@/lib/utils'

const RX_META = {
  yes: { label: 'Prescription required', tone: 'warning' },
  no: { label: 'Over the counter', tone: 'success' },
  unknown: { label: 'Rx status unknown', tone: 'neutral' },
}

function InfoTile({ label, value }) {
  if (!value) return null
  return (
    <div className="rounded-xl bg-surface-2 p-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-foreground">{value}</p>
    </div>
  )
}

function BulletList({ items }) {
  if (!items?.length) return null
  return (
    <ul className="space-y-1.5">
      {items.map((it, i) => (
        <li key={i} className="flex gap-2 text-sm text-foreground">
          <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
          <span>{titleCase(String(it))}</span>
        </li>
      ))}
    </ul>
  )
}

// One group of alternatives (generic / brand / similar) with reasons.
function AlternativeGroup({ icon: Icon, title, items, emptyHint }) {
  if (!items?.length) {
    return emptyHint ? (
      <div>
        <p className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Icon size={15} className="text-primary" /> {title}
        </p>
        <p className="text-sm text-muted">{emptyHint}</p>
      </div>
    ) : null
  }
  return (
    <div>
      <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon size={15} className="text-primary" /> {title}
      </p>
      <div className="space-y-2">
        {items.map((a, i) => (
          <div key={i} className="rounded-xl bg-surface-2 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-foreground">{titleCase(a.name)}</p>
              {a.match_score > 0 && <Badge tone="primary">{Math.round(a.match_score)}%</Badge>}
            </div>
            {a.reason && <p className="mt-1 text-sm text-muted">{a.reason}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

function MedicineCard({ rec }) {
  const di = rec.drug_info || {}
  const rx = RX_META[di.prescription_required] || RX_META.unknown
  const conf = Math.round(rec.confidence_score || 0)

  return (
    <Card className="animate-fade-up">
      {/* Header: detected medicine + confidence */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-primary-soft text-primary">
            <Pill size={22} />
          </span>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Detected medicine</p>
            <h3 className="text-lg font-bold leading-tight text-foreground">{titleCase(rec.detected_name)}</h3>
            {rec.matched && rec.resolved_name && titleCase(rec.resolved_name) !== titleCase(rec.detected_name) && (
              <p className="text-xs text-muted">Matched to <span className="font-medium text-foreground">{titleCase(rec.resolved_name)}</span> · {Math.round(rec.match_score)}%</p>
            )}
          </div>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted">Confidence</p>
          <p className="text-xl font-bold" style={{ color: confidenceColor(conf) }}>{conf}%</p>
        </div>
      </div>

      {!rec.matched && (
        <div className="mt-4 flex items-start gap-2 rounded-xl bg-warning/10 p-3 text-sm text-foreground">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
          <span>This medicine could not be confidently identified — please verify the name.</span>
        </div>
      )}

      {/* Drug information (Requirement 6) */}
      <div className="mt-5">
        <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Info size={15} className="text-primary" /> Drug information
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <InfoTile label="Generic / active" value={di.generic_name || '—'} />
          <InfoTile label="Brand" value={titleCase(di.brand_name || '')} />
          <InfoTile label="Drug class" value={di.drug_class || '—'} />
          <InfoTile label="Therapeutic category" value={di.therapeutic_category ? titleCase(di.therapeutic_category) : '—'} />
          <InfoTile label="Strengths" value={(di.available_strengths || []).join(', ') || '—'} />
          <div className="rounded-xl bg-surface-2 p-3">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Prescription</p>
            <Badge tone={rx.tone} className="mt-1">{rx.label}</Badge>
          </div>
        </div>
        {di.prescription_note && <p className="mt-2 text-xs text-muted">{di.prescription_note}</p>}
      </div>

      {/* Uses + side effects */}
      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        {di.common_uses?.length > 0 && (
          <div>
            <p className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-foreground">
              <Activity size={15} className="text-primary" /> Common uses
            </p>
            <BulletList items={di.common_uses.slice(0, 5)} />
          </div>
        )}
        {di.common_side_effects?.length > 0 && (
          <div>
            <p className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-foreground">
              <AlertTriangle size={15} className="text-warning" /> Side effects
            </p>
            <BulletList items={di.common_side_effects.slice(0, 6)} />
          </div>
        )}
      </div>

      {/* Warnings */}
      {rec.warnings?.length > 0 && (
        <div className="mt-5 rounded-xl border border-warning/30 bg-warning/5 p-3">
          <p className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-foreground">
            <ShieldCheck size={15} className="text-warning" /> Warnings
          </p>
          <BulletList items={rec.warnings} />
        </div>
      )}

      {/* Alternatives (Requirement 6) */}
      <div className="mt-5 space-y-4 rounded-xl bg-surface-2/50 p-4">
        <p className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Sparkles size={16} className="text-primary" /> Alternatives & equivalents
        </p>
        <AlternativeGroup icon={Replace} title="Generic equivalent" items={rec.generic_equivalents} emptyHint="No generic equivalent found in the dataset." />
        <AlternativeGroup icon={Layers} title="Brand alternatives" items={rec.brand_alternatives} emptyHint="No substitute brands found." />
        <AlternativeGroup icon={Beaker} title="Similar medicines" items={rec.similar_medicines} emptyHint="No same-class medicines found." />
      </div>

      {/* Pregnancy / food / storage */}
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        {di.pregnancy_safety && (
          <div className="rounded-xl bg-surface-2 p-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Baby size={13} className="text-primary" /> Pregnancy</p>
            <p className="mt-1 text-sm text-foreground">{di.pregnancy_safety}</p>
          </div>
        )}
        {di.food_interactions && (
          <div className="rounded-xl bg-surface-2 p-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Utensils size={13} className="text-primary" /> Food</p>
            <p className="mt-1 text-sm text-foreground">{di.food_interactions}</p>
          </div>
        )}
        {di.storage_instructions && (
          <div className="rounded-xl bg-surface-2 p-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Archive size={13} className="text-primary" /> Storage</p>
            <p className="mt-1 text-sm text-foreground">{di.storage_instructions}</p>
          </div>
        )}
      </div>

      {di.contraindications?.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-sm font-semibold text-foreground">Contraindications</p>
          <BulletList items={di.contraindications.slice(0, 5)} />
        </div>
      )}

      {/* AI summary */}
      {rec.ai_summary && (
        <div className="mt-5 rounded-xl bg-primary-soft/40 p-4">
          <p className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-foreground">
            <Sparkles size={15} className="text-primary" /> AI summary
          </p>
          <p className="whitespace-pre-wrap text-sm text-foreground">{rec.ai_summary}</p>
        </div>
      )}

      {/* Sources + related documents */}
      {(rec.rag_sources?.length > 0 || rec.related_documents?.length > 0) && (
        <div className="mt-5">
          <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
            <BookOpen size={15} className="text-primary" /> Sources
          </p>
          {rec.related_documents?.length > 0 && (
            <div className="space-y-2">
              {rec.related_documents.map((d, i) => (
                <div key={i} className="rounded-xl bg-surface-2 p-3">
                  <p className="flex items-center gap-1.5 text-xs font-semibold text-primary"><BookOpen size={13} /> {d.source}</p>
                  {d.excerpt && <p className="mt-1 line-clamp-3 text-sm text-muted">{d.excerpt}</p>}
                </div>
              ))}
            </div>
          )}
          {rec.rag_sources?.length > 0 && (
            <p className="mt-2 text-xs text-muted"><span className="font-medium text-foreground">References: </span>{rec.rag_sources.join(', ')}</p>
          )}
        </div>
      )}
    </Card>
  )
}

export default function MedicineRecommendations() {
  const [selected, setSelected] = useState([])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState([])

  const refreshHistory = () => {
    getMedicineRecommendations({ page: 1, page_size: 5 })
      .then((d) => setHistory(d.items || []))
      .catch(() => {})
  }

  useEffect(() => {
    refreshHistory()
  }, [])

  const run = async () => {
    if (selected.length === 0) {
      toast.error('Add at least one medicine')
      return
    }
    setLoading(true)
    try {
      const data = await recommendMedicines({
        medicines: selected,
        include_rag: true,
        max_alternatives: 5,
        persist: true,
      })
      setResult(data)
      refreshHistory()
    } catch (err) {
      toast.error(errorMessage(err, 'Could not generate recommendations'))
    } finally {
      setLoading(false)
    }
  }

  const openHistory = async (id) => {
    setLoading(true)
    try {
      setResult(await getMedicineRecommendation(id))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load that report'))
    } finally {
      setLoading(false)
    }
  }

  const medicines = result?.medicines ?? []

  return (
    <div className="space-y-5">
      {/* Disclaimer */}
      <div className="flex items-start gap-3 rounded-2xl border border-primary/20 bg-primary-soft/50 px-4 py-3">
        <Info size={18} className="mt-0.5 shrink-0 text-primary" />
        <p className="text-sm text-foreground">
          <span className="font-semibold">Educational information only.</span> Suggested
          alternatives and generic equivalents must only be substituted on the advice of a
          qualified doctor or pharmacist.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Input panel */}
        <div className="space-y-6 lg:col-span-2">
          <Card className="lg:sticky lg:top-24">
            <CardHeader icon={Sparkles} title="Medicine Recommendations" subtitle="Find generics, alternatives & drug info" />
            <TagInput
              value={selected}
              onChange={setSelected}
              suggestions={[]}
              placeholder="Type medicines e.g. Augmentin 625, Dolo 650"
              disabled={loading}
            />
            <p className="mt-2 text-xs text-muted">Press Enter or comma to add each medicine.</p>
            <div className="mt-5 flex gap-2">
              <Button className="flex-1" onClick={run} loading={loading} disabled={selected.length === 0}>
                <Sparkles size={16} /> Get Recommendations
              </Button>
              {selected.length > 0 && (
                <Button variant="ghost" onClick={() => { setSelected([]); setResult(null) }} disabled={loading}>Clear</Button>
              )}
            </div>
            <p className="mt-3 text-xs text-muted">Recommendations also run automatically after a prescription OCR scan.</p>
          </Card>

          {history.length > 0 && (
            <Card>
              <CardHeader icon={History} title="Recent reports" />
              <ul className="space-y-2">
                {history.map((h) => (
                  <li key={h.id}>
                    <button
                      onClick={() => openHistory(h.id)}
                      className="flex w-full items-center justify-between gap-2 rounded-xl bg-surface-2 p-3 text-left hover:bg-surface"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-foreground">
                          {(h.medicines || []).map((m) => titleCase(m)).join(', ') || `${h.medicine_count} medicine(s)`}
                        </p>
                        <p className="text-xs text-muted">{formatDate(h.created_at)}</p>
                      </div>
                      <Badge tone="primary">{Math.round(h.overall_confidence)}%</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        {/* Results panel */}
        <div className="space-y-4 lg:col-span-3">
          {loading && (<><CardSkeleton /><CardSkeleton /></>)}

          {!loading && !result && (
            <EmptyState
              icon={Sparkles}
              title="Medicine recommendations will appear here"
              description="Enter one or more medicines to see generic equivalents, brand alternatives, similar medicines, full drug information and evidence-based references."
            />
          )}

          {!loading && result && (
            <>
              {/* Overall AI report + confidence */}
              <Card className="border-primary/20 bg-primary-soft/30">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="grid h-11 w-11 place-items-center rounded-2xl bg-primary text-primary-foreground"><FileText size={22} /></span>
                    <div>
                      <h2 className="text-lg font-bold text-foreground">AI Recommendation Report</h2>
                      <p className="text-sm text-muted">{result.medicine_count} medicine(s) analysed</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-muted">Overall confidence</p>
                    <p className="text-2xl font-bold" style={{ color: confidenceColor(result.overall_confidence) }}>
                      {Math.round(result.overall_confidence)}%
                    </p>
                  </div>
                </div>
                {result.ai_report && (
                  <p className="mt-3 whitespace-pre-wrap text-sm text-foreground">{result.ai_report}</p>
                )}
                <div className="mt-3">
                  <ConfidenceBar value={result.overall_confidence} showLabel={false} />
                </div>
                {result.sources?.length > 0 && (
                  <p className="mt-3 text-xs text-muted"><span className="font-medium text-foreground">Sources: </span>{result.sources.join(', ')}</p>
                )}
              </Card>

              {result.warnings?.length > 0 && (
                <Card className="border-warning/30 bg-warning/5">
                  <div className="flex gap-3">
                    <AlertTriangle size={18} className="mt-0.5 shrink-0 text-warning" />
                    <ul className="space-y-1 text-sm text-foreground">
                      {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  </div>
                </Card>
              )}

              {medicines.length === 0 ? (
                <EmptyState icon={Stethoscope} title="No medicines analysed" description="Try entering a medicine name." />
              ) : (
                medicines.map((rec, i) => <MedicineCard key={i} rec={rec} />)
              )}

              {result.disclaimer && (
                <p className="px-2 text-center text-xs text-muted">{result.disclaimer}</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
