import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  Library,
  Sparkles,
  RotateCcw,
  History as HistoryIcon,
  ChevronRight,
  Copy,
  Download,
  Quote,
  BookOpen,
  MessageSquareText,
  Search,
  User,
  Bot,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import ConfidenceBar from '@/ui/ConfidenceBar'
import {
  queryEvidence,
  chatEvidence,
  getEvidenceHistory,
  getEvidenceRecord,
} from '@/lib/api'
import { generateEvidenceReportPdf } from '@/lib/pdf'
import { errorMessage, formatDate, cn } from '@/lib/utils'

const inputCls =
  'w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary'

// Minimal, safe markdown: escape, then render **bold** highlight markers from citation_builder.
function renderHighlighted(text = '') {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(/\*\*(.+?)\*\*/g, '<mark class="rounded bg-primary/20 px-0.5 text-primary">$1</mark>')
}

export default function EvidenceExplorer() {
  const [mode, setMode] = useState('query') // 'query' | 'chat'
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [turns, setTurns] = useState([]) // chat mode transcript: [{ role, content, result? }]
  const [sessionId, setSessionId] = useState(null)
  const [history, setHistory] = useState([])
  const resultRef = useRef(null)

  const refreshHistory = () =>
    getEvidenceHistory({ page_size: 8 }).then((d) => setHistory(d.items || [])).catch(() => setHistory([]))

  useEffect(() => {
    refreshHistory()
  }, [])

  const run = async () => {
    const text = input.trim()
    if (!text) {
      toast.error('Enter a medical question first.')
      return
    }
    setLoading(true)
    setInput('')
    try {
      if (mode === 'chat') {
        setTurns((t) => [...t, { role: 'user', content: text }])
        const data = await chatEvidence({ session_id: sessionId, message: text, persist: true })
        setSessionId(data.session_id)
        setTurns((t) => [...t, { role: 'assistant', content: data.response, result: data }])
        setResult(data)
      } else {
        const data = await queryEvidence({ query: text, persist: true })
        setResult(data)
      }
      refreshHistory()
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
    } catch (err) {
      toast.error(errorMessage(err, 'Evidence query failed. Is the backend running?'))
    } finally {
      setLoading(false)
    }
  }

  const openHistory = async (id) => {
    setLoading(true)
    try {
      const data = await getEvidenceRecord(id)
      setResult(data)
      setMode('query')
      setTurns([])
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load that evidence record.'))
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setInput('')
    setResult(null)
    setTurns([])
    setSessionId(null)
  }

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      {/* ---- Input panel ---- */}
      <div className="lg:col-span-2">
        <Card className="lg:sticky lg:top-24">
          <CardHeader
            icon={Library}
            title="Evidence Explorer"
            subtitle="Ask a medical question and get a response grounded in retrieved evidence"
          />

          <div className="mb-3 flex gap-1 rounded-xl bg-surface-2 p-1">
            <button
              onClick={() => { setMode('query'); reset() }}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 text-sm font-medium transition-colors',
                mode === 'query' ? 'bg-surface text-primary shadow-sm' : 'text-muted hover:text-foreground',
              )}
            >
              <Search size={14} /> Single Query
            </button>
            <button
              onClick={() => { setMode('chat'); reset() }}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 text-sm font-medium transition-colors',
                mode === 'chat' ? 'bg-surface text-primary shadow-sm' : 'text-muted hover:text-foreground',
              )}
            >
              <MessageSquareText size={14} /> Chat Session
            </button>
          </div>

          <div className="space-y-4">
            <label className="block">
              <span className="text-[11px] font-medium uppercase tracking-wide text-muted">
                {mode === 'chat' ? 'Message' : 'Medical question'}
              </span>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); run() }
                }}
                rows={mode === 'chat' ? 3 : 4}
                placeholder="e.g. What are the drug interactions of ibuprofen with paracetamol?"
                className={`mt-1 ${inputCls}`}
              />
            </label>

            <div className="flex gap-2">
              <Button className="flex-1" onClick={run} loading={loading}>
                <Sparkles size={16} /> {mode === 'chat' ? 'Send' : 'Get Evidence-Based Answer'}
              </Button>
              <Button variant="secondary" onClick={reset} aria-label="Reset"><RotateCcw size={16} /></Button>
            </div>
            <p className="text-xs text-muted">
              Every response is generated only after retrieving supporting passages from the medical
              knowledge base — reducing hallucination and giving you the evidence behind every answer.
            </p>
          </div>

          {history.length > 0 && (
            <div className="mt-6 border-t border-border pt-4">
              <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <HistoryIcon size={15} className="text-primary" /> Recent queries
              </p>
              <div className="space-y-2">
                {history.map((h) => (
                  <button
                    key={h.id}
                    onClick={() => openHistory(h.id)}
                    className="flex w-full items-center gap-3 rounded-xl border border-border bg-surface p-3 text-left transition-colors hover:bg-surface-2"
                  >
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-2 text-primary">
                      <Library size={16} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">{h.query || 'Evidence query'}</p>
                      <p className="truncate text-xs text-muted">
                        {formatDate(h.created_at)} · {Math.round(h.confidence_score)}% confidence
                      </p>
                    </div>
                    <Badge tone={h.evidence_found ? 'success' : 'neutral'}>{h.source_count} src</Badge>
                    <ChevronRight size={16} className="shrink-0 text-muted" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* ---- Result panel ---- */}
      <div ref={resultRef} className="lg:col-span-3 space-y-4">
        {mode === 'chat' && turns.length > 0 && (
          <div className="space-y-3">
            {turns.slice(0, -1).map((t, i) => (
              <div key={i} className={cn('flex gap-3', t.role === 'user' && 'flex-row-reverse')}>
                <span className={cn(
                  'grid h-8 w-8 shrink-0 place-items-center rounded-lg',
                  t.role === 'user' ? 'bg-surface-2 text-foreground' : 'bg-gradient-to-br from-primary to-accent text-white',
                )}>
                  {t.role === 'user' ? <User size={15} /> : <Bot size={15} />}
                </span>
                <div className={cn(
                  'max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
                  t.role === 'user' ? 'rounded-tr-sm bg-primary text-primary-foreground' : 'rounded-tl-sm bg-surface-2 text-foreground',
                )}>
                  {t.content}
                </div>
              </div>
            ))}
          </div>
        )}

        {result ? (
          <EvidenceResultCard result={result} chatFollowUp={mode === 'chat' && turns.length > 0} />
        ) : (
          <EmptyState
            icon={Library}
            title="Evidence-grounded answers will appear here"
            description="Ask a medical question. The engine retrieves relevant passages from the knowledge base, reranks them, generates a response grounded strictly in that evidence, and shows you every citation and retrieved chunk behind it."
          />
        )}
      </div>
    </div>
  )
}

// ============================================================
//  Result card — AI response, confidence, sources, citations,
//  expandable retrieved chunks, copy + download.
// ============================================================
function EvidenceResultCard({ result, chatFollowUp = false }) {
  const copyResponse = async () => {
    try {
      await navigator.clipboard.writeText(result.response || '')
      toast.success('Response copied to clipboard.')
    } catch {
      toast.error('Could not copy to clipboard.')
    }
  }

  const downloadReport = async () => {
    try {
      await generateEvidenceReportPdf({
        query: result.query,
        response: result.response,
        confidenceScore: result.confidence_score,
        citations: result.citations,
        retrievedChunks: result.retrieved_chunks,
        timestamp: result.timestamp,
      })
    } catch {
      toast.error('Could not generate the report PDF.')
    }
  }

  return (
    <div className="space-y-4">
      {/* AI Response */}
      <Card className="animate-fade-up">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-primary-soft text-primary">
              <Sparkles size={22} />
            </span>
            <div>
              <h3 className="font-semibold text-foreground">
                {chatFollowUp ? 'Latest Response' : 'AI Response'}
              </h3>
              <p className="text-xs text-muted">
                via {result.provider} · {formatDate(result.timestamp)}
                {!result.evidence_found && ' · no supporting evidence found'}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={copyResponse}>
              <Copy size={14} /> Copy
            </Button>
            <Button variant="secondary" size="sm" onClick={downloadReport}>
              <Download size={14} /> Download Report
            </Button>
          </div>
        </div>

        <p
          className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-foreground"
          dangerouslySetInnerHTML={{ __html: renderHighlighted(result.response || '') }}
        />

        <div className="mt-4 border-t border-border pt-4">
          <ConfidenceBar value={result.confidence_score || 0} />
        </div>

        {result.sources?.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-medium text-muted">Supporting sources:</span>
            {result.sources.map((s) => (
              <Badge key={s} tone="primary"><Quote size={11} /> {s}</Badge>
            ))}
          </div>
        )}

        <p className="mt-3 text-[11px] text-muted">{result.disclaimer}</p>
      </Card>

      {/* Citations */}
      {result.citations?.length > 0 && (
        <Card className="animate-fade-up">
          <CardHeader
            icon={Quote}
            title="Supporting Evidence"
            subtitle={`${result.citations.length} citation(s) backing this response`}
          />
          <div className="space-y-2">
            {result.citations.map((c) => (
              <div key={c.citation_id} className="rounded-xl border border-border bg-surface p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-foreground">[{c.citation_id}] {c.source_title}</p>
                  <Badge tone="success">{Math.round((c.similarity_score || 0) * 100)}%</Badge>
                </div>
                {c.snippet && (
                  <p
                    className="mt-1 border-l-2 border-primary/40 pl-2 text-xs leading-relaxed text-muted"
                    dangerouslySetInnerHTML={{ __html: renderHighlighted(c.snippet) }}
                  />
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Expandable retrieved chunks */}
      {result.retrieved_chunks?.length > 0 && (
        <Card className="animate-fade-up">
          <CardHeader
            icon={BookOpen}
            title="Retrieved Chunks"
            subtitle={`${result.retrieved_chunks.length} passage(s) retrieved from the knowledge base`}
          />
          <div className="space-y-2">
            {result.retrieved_chunks.map((c) => (
              <details key={c.chunk_id} className="group rounded-xl border border-border bg-surface p-3">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">{c.source_title}</span>
                  <span className="flex items-center gap-2 text-xs text-muted">
                    <Badge tone="neutral">{Math.round((c.rerank_score || c.similarity_score || 0) * 100)}% relevance</Badge>
                    <ChevronRight size={14} className="transition-transform group-open:rotate-90" />
                  </span>
                </summary>
                <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted">{c.text}</p>
              </details>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
