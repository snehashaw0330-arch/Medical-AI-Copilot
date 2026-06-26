import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  History,
  Search,
  Pill,
  ScanLine,
  Gauge,
  Timer,
  CheckCircle2,
  XCircle,
  Trash2,
  FileDown,
  FileJson,
  Eye,
  X,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Activity,
  HeartPulse,
  Calendar,
  ArrowDownWideNarrow,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import {
  getHistory,
  getHistoryStats,
  getHistoryMedicines,
  getHistoryItem,
  deleteHistoryItem,
  clearHistory,
  historyImageUrl,
} from '@/lib/api'
import { generatePrescriptionPdf, urlToDataUrl } from '@/lib/pdf'
import { formatDate, titleCase, confidenceColor, pct, freqText, errorMessage } from '@/lib/utils'

const PAGE_SIZE = 8

// Trigger a client-side file download from an in-memory blob.
function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ============================================================
//  Statistics cards
// ============================================================
function StatCard({ icon: Icon, label, value, tone = 'primary' }) {
  const toneClass = {
    primary: 'bg-primary-soft text-primary',
    success: 'bg-success/15 text-success',
    danger: 'bg-danger/15 text-danger',
  }[tone]
  return (
    <Card className="flex items-center gap-3">
      <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${toneClass}`}>
        <Icon size={20} />
      </span>
      <div className="min-w-0">
        <p className="text-xs text-muted">{label}</p>
        <p className="text-xl font-bold text-foreground">{value}</p>
      </div>
    </Card>
  )
}

// ============================================================
//  One history row
// ============================================================
function HistoryRow({ item, busy, onView, onPdf, onJson, onDelete }) {
  const failed = item.status === 'failed'
  const conf = pct(item.confidence)
  return (
    <div className="flex items-start gap-3 border-b border-border py-3 last:border-0">
      <span
        className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg ${
          failed ? 'bg-danger/15 text-danger' : 'bg-success/15 text-success'
        }`}
      >
        {failed ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            onClick={onView}
            className="flex items-center gap-1.5 truncate text-left text-sm font-medium text-foreground hover:text-primary"
          >
            <ScanLine size={14} className="shrink-0 text-muted" />
            <span className="truncate">{item.filename || 'Prescription'}</span>
          </button>
          {failed ? (
            <Badge tone="danger">Failed</Badge>
          ) : (
            <span
              className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold"
              style={{ color: confidenceColor(conf), backgroundColor: `${confidenceColor(conf)}1a` }}
            >
              {conf}%
            </span>
          )}
        </div>

        <p className="mt-1 text-xs text-muted">
          {formatDate(item.created_at)}
          {item.engine ? <> · engine <span className="font-medium text-foreground">{item.engine}</span></> : null}
          {' · '}{item.medicine_count} medicine{item.medicine_count === 1 ? '' : 's'}
          {' · '}{item.processing_time}s
        </p>

        {item.medicine_names?.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {item.medicine_names.slice(0, 6).map((m, i) => (
              <Badge key={i} tone="primary">{titleCase(m)}</Badge>
            ))}
            {item.medicine_names.length > 6 && (
              <Badge tone="neutral">+{item.medicine_names.length - 6} more</Badge>
            )}
          </div>
        )}
      </div>

      {/* Row actions */}
      <div className="flex shrink-0 items-center gap-1">
        <IconButton title="View report" onClick={onView} disabled={busy}><Eye size={15} /></IconButton>
        <IconButton title="Download PDF" onClick={onPdf} disabled={busy}><FileDown size={15} /></IconButton>
        <IconButton title="Download JSON" onClick={onJson} disabled={busy}><FileJson size={15} /></IconButton>
        <IconButton title="Delete" onClick={onDelete} disabled={busy} danger><Trash2 size={15} /></IconButton>
      </div>
    </div>
  )
}

function IconButton({ title, onClick, disabled, danger, children }) {
  return (
    <button
      title={title}
      aria-label={title}
      onClick={onClick}
      disabled={disabled}
      className={`grid h-8 w-8 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 disabled:opacity-40 ${
        danger ? 'hover:text-danger' : 'hover:text-primary'
      }`}
    >
      {children}
    </button>
  )
}

// ============================================================
//  Detail modal
// ============================================================
function MedicineBlock({ m }) {
  const conf = pct(m.confidence)
  const name = m.name ? titleCase(m.name) : m.raw_text
  const d = m.details
  return (
    <div className="rounded-xl bg-surface-2 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold text-foreground">
          <Pill size={16} className="text-primary" /> {name}
        </p>
        <span className="text-xs font-semibold" style={{ color: confidenceColor(conf) }}>{conf}%</span>
      </div>
      <p className="mt-1 text-xs text-muted">
        Dosage: {m.dosage || '—'} · Frequency: {freqText(m) || '—'} · Duration: {m.duration || '—'}
      </p>
      {(d?.uses?.length || d?.side_effects?.length) && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {d?.uses?.length > 0 && (
            <p className="text-xs text-muted">
              <span className="flex items-center gap-1 font-medium text-foreground"><Activity size={12} className="text-primary" /> Uses</span>
              {d.uses.slice(0, 3).join(', ')}
            </p>
          )}
          {d?.side_effects?.length > 0 && (
            <p className="text-xs text-muted">
              <span className="flex items-center gap-1 font-medium text-foreground"><HeartPulse size={12} className="text-primary" /> Side effects</span>
              {d.side_effects.slice(0, 4).join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function DetailModal({ record, onClose, onPdf, onJson, onDelete, busy }) {
  if (!record) return null
  const conf = pct(record.confidence)
  const failed = record.status === 'failed'
  const meds = record.medicines || []
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm">
      <Card className="my-8 w-full max-w-3xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <CardHeader
            icon={ScanLine}
            title={record.filename || 'Prescription'}
            subtitle={`${formatDate(record.created_at)} · ${record.provider || record.engine || 'OCR'}`}
          />
          <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        {/* Summary chips */}
        <div className="mb-4 flex flex-wrap gap-2">
          <Badge tone={failed ? 'danger' : 'success'}>{failed ? 'Failed' : 'Success'}</Badge>
          {!failed && (
            <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold"
              style={{ color: confidenceColor(conf), backgroundColor: `${confidenceColor(conf)}1a` }}>
              <Gauge size={12} /> {conf}% confidence
            </span>
          )}
          <Badge tone="neutral"><Timer size={12} /> {record.processing_time}s</Badge>
          <Badge tone="neutral"><Pill size={12} /> {record.medicine_count} medicines</Badge>
        </div>

        {failed && record.error && (
          <div className="mb-4 rounded-xl bg-danger/10 p-3 text-sm text-foreground">{record.error}</div>
        )}

        <div className="grid gap-5 md:grid-cols-2">
          {/* Image */}
          {record.has_image && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Uploaded prescription</p>
              <img
                src={historyImageUrl(record.id)}
                alt="Prescription"
                className="max-h-80 w-full rounded-xl border border-border bg-surface-2 object-contain"
              />
            </div>
          )}

          {/* OCR text */}
          <div className={record.has_image ? '' : 'md:col-span-2'}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">OCR text</p>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-xl bg-surface-2 p-3 text-xs text-muted">
              {record.raw_text || 'No text extracted.'}
            </pre>
          </div>
        </div>

        {/* Medicines + drug info */}
        {meds.length > 0 && (
          <div className="mt-5">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Medicines & drug information</p>
            <div className="grid gap-2">
              {meds.map((m, i) => <MedicineBlock key={i} m={m} />)}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onJson} disabled={busy}><FileJson size={15} /> JSON</Button>
          <Button variant="secondary" size="sm" onClick={onPdf} disabled={busy}><FileDown size={15} /> PDF</Button>
          <Button variant="danger" size="sm" onClick={onDelete} disabled={busy}><Trash2 size={15} /> Delete</Button>
        </div>
      </Card>
    </div>
  )
}

// ============================================================
//  Page
// ============================================================
export default function PrescriptionHistory() {
  const [stats, setStats] = useState(null)
  const [data, setData] = useState({ items: [], total: 0, page: 1, pages: 0 })
  const [medicines, setMedicines] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [detail, setDetail] = useState(null)

  // Filters
  const [search, setSearch] = useState('')      // bound to the input
  const [query, setQuery] = useState('')         // debounced value used for fetching
  const [medicine, setMedicine] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sort, setSort] = useState('newest')
  const [page, setPage] = useState(1)

  // Debounce the search box (300ms) and reset to page 1 on change.
  useEffect(() => {
    const t = setTimeout(() => { setQuery(search); setPage(1) }, 300)
    return () => clearTimeout(t)
  }, [search])

  const loadStats = useCallback(async () => {
    try {
      const [s, meds] = await Promise.all([getHistoryStats(), getHistoryMedicines()])
      setStats(s)
      setMedicines(meds)
    } catch { /* non-fatal: stats are supplementary */ }
  }, [])

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getHistory({
        q: query,
        medicine,
        sort,
        page,
        page_size: PAGE_SIZE,
        date_from: dateFrom || undefined,
        // Make the upper bound inclusive of the whole selected day.
        date_to: dateTo ? `${dateTo}T23:59:59` : undefined,
      })
      setData(res)
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load history'))
    } finally {
      setLoading(false)
    }
  }, [query, medicine, sort, page, dateFrom, dateTo])

  // Data-fetching effects: these intentionally set a loading flag before the
  // request resolves, which is the canonical pattern for fetch-on-mount/deps.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadStats() }, [loadStats])
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadList() }, [loadList])

  const refresh = () => { loadList(); loadStats() }

  // ---- record actions (fetch full detail on demand for downloads) ----
  const openDetail = async (id) => {
    setBusyId(id)
    try {
      setDetail(await getHistoryItem(id))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not open record'))
    } finally {
      setBusyId(null)
    }
  }

  const fullRecord = async (id) => (detail?.id === id ? detail : getHistoryItem(id))

  const downloadJson = async (id) => {
    setBusyId(id)
    try {
      const rec = await fullRecord(id)
      downloadBlob(
        `medisense-history-${(rec.filename || rec.id).replace(/\.[^.]+$/, '')}.json`,
        new Blob([JSON.stringify(rec, null, 2)], { type: 'application/json' }),
      )
    } catch (err) {
      toast.error(errorMessage(err, 'Could not export JSON'))
    } finally {
      setBusyId(null)
    }
  }

  const downloadPdf = async (id) => {
    setBusyId(id)
    try {
      const rec = await fullRecord(id)
      const imageDataUrl = rec.has_image ? await urlToDataUrl(historyImageUrl(rec.id)) : null
      await generatePrescriptionPdf({
        meds: rec.medicines || [],
        fields: rec.fields || {},
        score: pct(rec.confidence),
        imageDataUrl,
        fileName: rec.filename,
        notes: rec.doctor_notes,
      })
    } catch (err) {
      toast.error(errorMessage(err, 'Could not generate PDF'))
    } finally {
      setBusyId(null)
    }
  }

  const removeRecord = async (id) => {
    setBusyId(id)
    try {
      await deleteHistoryItem(id)
      toast.success('Record deleted')
      if (detail?.id === id) setDetail(null)
      // If we just emptied the current page, step back one.
      if (data.items.length === 1 && page > 1) setPage((p) => p - 1)
      else refresh()
    } catch (err) {
      toast.error(errorMessage(err, 'Could not delete record'))
    } finally {
      setBusyId(null)
    }
  }

  const wipeAll = async () => {
    if (!window.confirm('Delete the entire prescription history? This cannot be undone.')) return
    try {
      const res = await clearHistory()
      toast.success(res.message || 'History cleared')
      setPage(1)
      refresh()
    } catch (err) {
      toast.error(errorMessage(err, 'Could not clear history'))
    }
  }

  const hasActiveFilters = query || medicine || dateFrom || dateTo
  const showEmpty = !loading && data.items.length === 0

  const statCards = useMemo(
    () => [
      { icon: History, label: 'Total Analyses', value: stats?.total_analyses ?? 0, tone: 'primary' },
      { icon: CheckCircle2, label: 'Successful', value: stats?.successful_analyses ?? 0, tone: 'success' },
      { icon: XCircle, label: 'Failed', value: stats?.failed_analyses ?? 0, tone: 'danger' },
      { icon: Gauge, label: 'Avg. Confidence', value: `${pct(stats?.average_confidence)}%`, tone: 'primary' },
      { icon: Timer, label: 'Avg. Time', value: `${(stats?.average_processing_time ?? 0).toFixed(2)}s`, tone: 'primary' },
    ],
    [stats],
  )

  return (
    <div className="space-y-6">
      {/* Statistics */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {statCards.map((c) => <StatCard key={c.label} {...c} />)}
      </section>

      {/* Toolbar + list */}
      <Card>
        <CardHeader
          icon={History}
          title="Prescription History"
          subtitle="Every analysis from the OCR pipeline, stored server-side"
          action={
            stats?.total_analyses > 0 && (
              <Button variant="ghost" size="sm" onClick={wipeAll}>
                <Trash2 size={15} /> Clear all
              </Button>
            )
          }
        />

        {/* Filters */}
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          <label className="relative block">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search file, text or medicine…"
              className="h-10 w-full rounded-xl border border-border bg-background pl-9 pr-3 text-sm text-foreground outline-none focus:border-primary"
            />
          </label>

          <label className="relative block">
            <Pill size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <select
              value={medicine}
              onChange={(e) => { setMedicine(e.target.value); setPage(1) }}
              className="h-10 w-full appearance-none rounded-xl border border-border bg-background pl-9 pr-3 text-sm text-foreground outline-none focus:border-primary"
            >
              <option value="">All medicines</option>
              {medicines.map((m) => <option key={m} value={m}>{titleCase(m)}</option>)}
            </select>
          </label>

          <div className="flex items-center gap-2">
            <Calendar size={16} className="shrink-0 text-muted" />
            <input
              type="date" value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(1) }}
              className="h-10 w-full rounded-xl border border-border bg-background px-2 text-sm text-foreground outline-none focus:border-primary"
            />
            <span className="text-muted">–</span>
            <input
              type="date" value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setPage(1) }}
              className="h-10 w-full rounded-xl border border-border bg-background px-2 text-sm text-foreground outline-none focus:border-primary"
            />
          </div>

          <label className="relative block">
            <ArrowDownWideNarrow size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <select
              value={sort}
              onChange={(e) => { setSort(e.target.value); setPage(1) }}
              className="h-10 w-full appearance-none rounded-xl border border-border bg-background pl-9 pr-3 text-sm text-foreground outline-none focus:border-primary"
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="confidence">Highest confidence</option>
            </select>
          </label>
        </div>

        {/* List */}
        <div className="mt-5">
          {loading && data.items.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-14 text-muted">
              <Loader2 size={26} className="animate-spin text-primary" />
              <p className="text-sm">Loading history…</p>
            </div>
          ) : showEmpty ? (
            <EmptyState
              icon={History}
              title={hasActiveFilters ? 'No matching records' : 'No history yet'}
              description={
                hasActiveFilters
                  ? 'Try adjusting your search or filters.'
                  : 'Analyze a prescription on the OCR page — every analysis is saved here automatically.'
              }
            />
          ) : (
            <div className={loading ? 'opacity-60 transition-opacity' : ''}>
              {data.items.map((item) => (
                <HistoryRow
                  key={item.id}
                  item={item}
                  busy={busyId === item.id}
                  onView={() => openDetail(item.id)}
                  onPdf={() => downloadPdf(item.id)}
                  onJson={() => downloadJson(item.id)}
                  onDelete={() => removeRecord(item.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {data.pages > 1 && (
          <div className="mt-4 flex items-center justify-between border-t border-border pt-4 text-sm">
            <span className="text-muted">
              Page {data.page} of {data.pages} · {data.total} record{data.total === 1 ? '' : 's'}
            </span>
            <div className="flex gap-1.5">
              <Button
                variant="secondary" size="sm"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft size={15} /> Prev
              </Button>
              <Button
                variant="secondary" size="sm"
                disabled={page >= data.pages || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Next <ChevronRight size={15} />
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Detail modal */}
      <DetailModal
        record={detail}
        busy={busyId === detail?.id}
        onClose={() => setDetail(null)}
        onPdf={() => downloadPdf(detail.id)}
        onJson={() => downloadJson(detail.id)}
        onDelete={() => removeRecord(detail.id)}
      />
    </div>
  )
}
