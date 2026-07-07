import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  ScrollText, Search, AlertTriangle, RefreshCw, FileJson, FileText, Sheet,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import { CardSkeleton } from '@/ui/Skeleton'
import { getAuditLogs, governanceExportUrl } from '@/lib/api'
import { errorMessage, formatDate } from '@/lib/utils'

const statusTone = (code) => (code >= 500 ? 'danger' : code >= 400 ? 'warning' : code >= 200 ? 'success' : 'neutral')
const methodTone = { GET: 'primary', POST: 'success', DELETE: 'danger', PUT: 'warning', PATCH: 'warning' }

export default function AuditLogs() {
  const [page, setPage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({ api: '', method: '', errors_only: false, page: 1 })

  const load = async (override = {}) => {
    setLoading(true)
    const f = { ...filters, ...override }
    setFilters(f)
    try {
      setPage(await getAuditLogs({ ...f, page_size: 50 }))
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load audit logs'))
    } finally { setLoading(false) }
  }
  useEffect(() => {
    let alive = true
    getAuditLogs({ page_size: 50 })
      .then((p) => alive && setPage(p))
      .catch((err) => toast.error(errorMessage(err, 'Could not load audit logs')))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  const items = page?.items || []

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-foreground"><ScrollText size={22} className="text-primary" /> Audit Logs</h1>
          <p className="text-sm text-muted">Every API request — user, endpoint, status, duration and errors. PHI-masked.</p>
        </div>
        <div className="flex items-center gap-2">
          <a href={governanceExportUrl('audit-logs', 'csv')}><Button variant="secondary"><Sheet size={15} /> CSV</Button></a>
          <a href={governanceExportUrl('audit-logs', 'json')}><Button variant="secondary"><FileJson size={15} /> JSON</Button></a>
          <a href={governanceExportUrl('audit-logs', 'pdf')}><Button variant="secondary"><FileText size={15} /> PDF</Button></a>
        </div>
      </div>

      <Card>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex-1"><span className="mb-1 block text-xs font-medium text-muted">Endpoint</span>
            <input value={filters.api} onChange={(e) => setFilters((f) => ({ ...f, api: e.target.value }))}
              onKeyDown={(e) => e.key === 'Enter' && load({ page: 1 })} placeholder="/ocr, /governance…"
              className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary" />
          </label>
          <label><span className="mb-1 block text-xs font-medium text-muted">Method</span>
            <select value={filters.method} onChange={(e) => setFilters((f) => ({ ...f, method: e.target.value }))}
              className="h-10 rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary">
              <option value="">All</option>{['GET', 'POST', 'DELETE', 'PUT', 'PATCH'].map((m) => <option key={m}>{m}</option>)}
            </select>
          </label>
          <label className="flex h-10 cursor-pointer items-center gap-2 rounded-xl border border-border bg-background px-3 text-sm text-foreground">
            <input type="checkbox" checked={filters.errors_only} onChange={(e) => setFilters((f) => ({ ...f, errors_only: e.target.checked }))} />
            <AlertTriangle size={14} className="text-warning" /> Errors only
          </label>
          <Button variant="primary" onClick={() => load({ page: 1 })}><Search size={15} /> Search</Button>
          <Button variant="ghost" onClick={() => load({ api: '', method: '', errors_only: false, page: 1 })}><RefreshCw size={15} /></Button>
        </div>
      </Card>

      {loading && <CardSkeleton />}

      {!loading && items.length === 0 && (
        <EmptyState icon={ScrollText} title="No audit entries" description="API requests are logged automatically as the app is used." />
      )}

      {!loading && items.length > 0 && (
        <Card>
          <CardHeader icon={ScrollText} title={`${page.total} entries`} subtitle={`Page ${page.page} of ${page.pages}`} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <th className="py-2 pr-3 font-medium">When</th>
                  <th className="py-2 pr-3 font-medium">User</th>
                  <th className="py-2 pr-3 font-medium">Method</th>
                  <th className="py-2 pr-3 font-medium">Endpoint</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Time</th>
                  <th className="py-2 pr-3 font-medium">Error</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id} className="border-b border-border/60 hover:bg-surface-2">
                    <td className="py-2.5 pr-3 text-muted">{formatDate(r.created_at)}</td>
                    <td className="py-2.5 pr-3 font-mono text-xs text-foreground">{r.user}</td>
                    <td className="py-2.5 pr-3"><Badge tone={methodTone[r.method] || 'neutral'}>{r.method}</Badge></td>
                    <td className="py-2.5 pr-3 font-mono text-xs text-foreground">{r.api}</td>
                    <td className="py-2.5 pr-3"><Badge tone={statusTone(r.status_code)}>{r.status_code}</Badge></td>
                    <td className="py-2.5 pr-3 text-muted">{(r.processing_time_ms || 0).toFixed(0)} ms</td>
                    <td className="py-2.5 pr-3 max-w-[200px] truncate text-danger">{r.error || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {page.pages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <Button variant="secondary" disabled={page.page <= 1} onClick={() => load({ page: page.page - 1 })}>Previous</Button>
              <span className="text-sm text-muted">Page {page.page} / {page.pages}</span>
              <Button variant="secondary" disabled={page.page >= page.pages} onClick={() => load({ page: page.page + 1 })}>Next</Button>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
