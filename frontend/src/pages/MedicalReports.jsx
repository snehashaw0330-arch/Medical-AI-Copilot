import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  FileText,
  Search,
  Calendar,
  User,
  Eye,
  FileDown,
  FileJson,
  FileCode2,
  Trash2,
  X,
  ChevronLeft,
  ChevronRight,
  Loader2,
  FileStack,
  CalendarClock,
  Gauge,
  ShieldAlert,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import ReportViewer from '@/ui/ReportViewer'
import {
  getReports,
  getReportStats,
  getReport,
  deleteReport,
  fetchReportBlob,
} from '@/lib/api'
import { formatDate, titleCase, confidenceColor, pct, errorMessage } from '@/lib/utils'

const PAGE_SIZE = 8

// Risk level → badge tone (mirrors ClinicalReport / backend RiskLevel).
const RISK_TONE = { critical: 'danger', high: 'danger', moderate: 'warning', low: 'primary' }

// Trigger a client-side download from an in-memory blob.
function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ============================================================
//  Stat card
// ============================================================
function StatCard({ icon: Icon, label, value, tone = 'primary' }) {
  const toneClass = {
    primary: 'bg-primary-soft text-primary',
    success: 'bg-success/15 text-success',
    warning: 'bg-warning/15 text-warning',
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
//  One report row
// ============================================================
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

function ReportRow({ item, busy, onView, onPdf, onJson, onHtml, onDelete }) {
  const conf = pct(item.overall_confidence)
  const tone = RISK_TONE[item.risk_level] || 'neutral'
  return (
    <div className="flex items-start gap-3 border-b border-border py-3 last:border-0">
      <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary">
        <FileText size={16} />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            onClick={onView}
            className="flex items-center gap-1.5 truncate text-left text-sm font-medium text-foreground hover:text-primary"
          >
            <span className="truncate">{item.filename || 'Report'}</span>
          </button>
          <div className="flex items-center gap-2">
            {item.risk_level && <Badge tone={tone}>{titleCase(item.risk_level)}</Badge>}
            <span
              className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold"
              style={{ color: confidenceColor(conf), backgroundColor: `${confidenceColor(conf)}1a` }}
            >
              {conf}%
            </span>
          </div>
        </div>

        <p className="mt-1 text-xs text-muted">
          {formatDate(item.created_at)}
          {item.patient_name ? <> · <span className="font-medium text-foreground">{item.patient_name}</span></> : null}
          {' · '}{item.medicine_count} medicine{item.medicine_count === 1 ? '' : 's'}
          {item.top_disease ? <> · {titleCase(item.top_disease)}</> : null}
        </p>
      </div>

      {/* Row actions */}
      <div className="flex shrink-0 items-center gap-1">
        <IconButton title="View report" onClick={onView} disabled={busy}><Eye size={15} /></IconButton>
        <IconButton title="Download PDF" onClick={onPdf} disabled={busy}><FileDown size={15} /></IconButton>
        <IconButton title="Download JSON" onClick={onJson} disabled={busy}><FileJson size={15} /></IconButton>
        <IconButton title="Download HTML" onClick={onHtml} disabled={busy}><FileCode2 size={15} /></IconButton>
        <IconButton title="Delete" onClick={onDelete} disabled={busy} danger><Trash2 size={15} /></IconButton>
      </div>
    </div>
  )
}

// ============================================================
//  Viewer modal
// ============================================================
function ViewerModal({ report, busy, onClose, onPdf, onJson, onHtml, onDelete }) {
  if (!report) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm">
      <div className="my-8 w-full max-w-3xl">
        <Card className="mb-3 flex items-center justify-between">
          <CardHeader
            icon={FileText}
            title={report.content?.filename || 'Medical Report'}
            subtitle={report.created_at ? formatDate(report.created_at) : undefined}
          />
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={onPdf} disabled={busy}><FileDown size={15} /> PDF</Button>
            <Button variant="secondary" size="sm" onClick={onJson} disabled={busy}><FileJson size={15} /> JSON</Button>
            <Button variant="secondary" size="sm" onClick={onHtml} disabled={busy}><FileCode2 size={15} /> HTML</Button>
            <Button variant="danger" size="sm" onClick={onDelete} disabled={busy}><Trash2 size={15} /></Button>
            <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-foreground">
              <X size={18} />
            </button>
          </div>
        </Card>
        <ReportViewer report={report} />
      </div>
    </div>
  )
}

// ============================================================
//  Page
// ============================================================
export default function MedicalReports() {
  const [stats, setStats] = useState(null)
  const [data, setData] = useState({ items: [], total: 0, page: 1, pages: 0 })
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const [detail, setDetail] = useState(null)

  // Filters
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [patient, setPatient] = useState('')
  const [patientQuery, setPatientQuery] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)

  // Debounce the text inputs (300ms), reset to page 1 on change.
  useEffect(() => {
    const t = setTimeout(() => { setQuery(search); setPage(1) }, 300)
    return () => clearTimeout(t)
  }, [search])
  useEffect(() => {
    const t = setTimeout(() => { setPatientQuery(patient); setPage(1) }, 300)
    return () => clearTimeout(t)
  }, [patient])

  const loadStats = useCallback(async () => {
    try { setStats(await getReportStats()) } catch { /* supplementary */ }
  }, [])

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      setData(await getReports({
        q: query,
        patient: patientQuery,
        page,
        page_size: PAGE_SIZE,
        date_from: dateFrom || undefined,
        date_to: dateTo ? `${dateTo}T23:59:59` : undefined,
      }))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load reports'))
    } finally {
      setLoading(false)
    }
  }, [query, patientQuery, page, dateFrom, dateTo])

  // Fetch-on-deps: setting a loading flag before the request resolves is the
  // canonical pattern here (mirrors PrescriptionHistory).
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadStats() }, [loadStats])
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadList() }, [loadList])

  const refresh = () => { loadList(); loadStats() }

  const openDetail = async (id) => {
    setBusyId(id)
    try {
      setDetail(await getReport(id))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not open report'))
    } finally {
      setBusyId(null)
    }
  }

  const download = async (id, format, ext = format) => {
    setBusyId(id)
    try {
      const blob = await fetchReportBlob(id, format)
      const name = detail?.id === id ? detail?.content?.filename : id
      downloadBlob(`medisense-report-${String(name || id).replace(/\.[^.]+$/, '')}.${ext}`, blob)
    } catch (err) {
      toast.error(errorMessage(err, `Could not download ${format.toUpperCase()}`))
    } finally {
      setBusyId(null)
    }
  }

  const removeReport = async (id) => {
    if (!window.confirm('Delete this report? This cannot be undone.')) return
    setBusyId(id)
    try {
      await deleteReport(id)
      toast.success('Report deleted')
      if (detail?.id === id) setDetail(null)
      if (data.items.length === 1 && page > 1) setPage((p) => p - 1)
      else refresh()
    } catch (err) {
      toast.error(errorMessage(err, 'Could not delete report'))
    } finally {
      setBusyId(null)
    }
  }

  const hasActiveFilters = query || patientQuery || dateFrom || dateTo
  const showEmpty = !loading && data.items.length === 0

  const statCards = useMemo(() => [
    { icon: FileStack, label: 'Total Reports', value: stats?.total_reports ?? 0, tone: 'primary' },
    { icon: CalendarClock, label: 'Generated Today', value: stats?.reports_today ?? 0, tone: 'success' },
    { icon: Gauge, label: 'Avg. OCR Confidence', value: `${pct(stats?.average_confidence)}%`, tone: 'primary' },
    { icon: ShieldAlert, label: 'High Risk Reports', value: stats?.high_risk_reports ?? 0, tone: 'danger' },
  ], [stats])

  return (
    <div className="space-y-6">
      {/* Stats */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((c) => <StatCard key={c.label} {...c} />)}
      </section>

      {/* Toolbar + list */}
      <Card>
        <CardHeader
          icon={FileText}
          title="Medical Reports"
          subtitle="Comprehensive reports generated from every OCR analysis"
        />

        {/* Filters */}
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          <label className="relative block">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search file or medicine…"
              className="h-10 w-full rounded-xl border border-border bg-background pl-9 pr-3 text-sm text-foreground outline-none focus:border-primary"
            />
          </label>

          <label className="relative block">
            <User size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              value={patient}
              onChange={(e) => setPatient(e.target.value)}
              placeholder="Filter by patient…"
              className="h-10 w-full rounded-xl border border-border bg-background pl-9 pr-3 text-sm text-foreground outline-none focus:border-primary"
            />
          </label>

          <div className="flex items-center gap-2 lg:col-span-2">
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
        </div>

        {/* List */}
        <div className="mt-5">
          {loading && data.items.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-14 text-muted">
              <Loader2 size={26} className="animate-spin text-primary" />
              <p className="text-sm">Loading reports…</p>
            </div>
          ) : showEmpty ? (
            <EmptyState
              icon={FileText}
              title={hasActiveFilters ? 'No matching reports' : 'No reports yet'}
              description={
                hasActiveFilters
                  ? 'Try adjusting your search or filters.'
                  : 'Analyze a prescription on the OCR page — a report is generated automatically for every analysis.'
              }
            />
          ) : (
            <div className={loading ? 'opacity-60 transition-opacity' : ''}>
              {data.items.map((item) => (
                <ReportRow
                  key={item.id}
                  item={item}
                  busy={busyId === item.id}
                  onView={() => openDetail(item.id)}
                  onPdf={() => download(item.id, 'pdf')}
                  onJson={() => download(item.id, 'json')}
                  onHtml={() => download(item.id, 'html')}
                  onDelete={() => removeReport(item.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {data.pages > 1 && (
          <div className="mt-4 flex items-center justify-between border-t border-border pt-4 text-sm">
            <span className="text-muted">
              Page {data.page} of {data.pages} · {data.total} report{data.total === 1 ? '' : 's'}
            </span>
            <div className="flex gap-1.5">
              <Button variant="secondary" size="sm" disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}>
                <ChevronLeft size={15} /> Prev
              </Button>
              <Button variant="secondary" size="sm" disabled={page >= data.pages || loading}
                onClick={() => setPage((p) => p + 1)}>
                Next <ChevronRight size={15} />
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Viewer modal */}
      <ViewerModal
        report={detail}
        busy={busyId === detail?.id}
        onClose={() => setDetail(null)}
        onPdf={() => download(detail.id, 'pdf')}
        onJson={() => download(detail.id, 'json')}
        onHtml={() => download(detail.id, 'html')}
        onDelete={() => removeReport(detail.id)}
      />
    </div>
  )
}
