import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  BookOpen,
  UploadCloud,
  RefreshCw,
  Search,
  FileText,
  Sparkles,
  Database,
  Cpu,
  Layers,
  Quote,
  AlertTriangle,
  Loader2,
} from 'lucide-react'
import Card, { CardHeader } from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import EmptyState from '@/ui/EmptyState'
import {
  getRagStatus,
  rebuildRagIndex,
  queryKnowledgeBase,
  uploadKnowledgeDoc,
} from '@/lib/api'
import { errorMessage, confidenceColor } from '@/lib/utils'

const pct = (v) => Math.round((v || 0) * 100)

// ---------- presentational ----------
function StatPill({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-2 rounded-xl bg-surface-2 px-3 py-2">
      <Icon size={15} className="text-primary" />
      <span className="text-xs text-muted">{label}</span>
      <span className="ml-auto text-sm font-semibold text-foreground">{value}</span>
    </div>
  )
}

function ChunkCard({ chunk, rank }) {
  const score = pct(chunk.score)
  return (
    <div className="rounded-xl border border-border bg-surface-2 p-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <FileText size={13} className="text-primary" /> {chunk.source}
          <span className="text-muted">· chunk #{rank}</span>
        </span>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold"
          style={{ color: confidenceColor(score), backgroundColor: `${confidenceColor(score)}1a` }}
        >
          {chunk.score.toFixed(2)} similarity
        </span>
      </div>
      <p className="line-clamp-4 whitespace-pre-wrap text-xs leading-relaxed text-muted">{chunk.text}</p>
    </div>
  )
}

// ---------- page ----------
export default function KnowledgeBase() {
  const [status, setStatus] = useState(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [searching, setSearching] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  const refreshStatus = () => getRagStatus().then(setStatus).catch(() => setStatus(null))
  useEffect(() => { refreshStatus() }, [])

  const onUpload = async (file) => {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const res = await uploadKnowledgeDoc(file, { reindex: true })
      toast.success(`Added ${res.filename} · index rebuilt`)
      await refreshStatus()
    } catch (err) {
      setError(errorMessage(err, 'Upload failed.'))
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const rebuild = async () => {
    setIndexing(true)
    setError(null)
    try {
      const res = await rebuildRagIndex()
      toast.success(`Indexed ${res.indexed_chunks} chunks from ${res.documents} documents`)
      await refreshStatus()
    } catch (err) {
      setError(errorMessage(err, 'Indexing failed. Are the RAG dependencies installed?'))
    } finally {
      setIndexing(false)
    }
  }

  const search = async (q = question) => {
    const text = q.trim()
    if (!text || searching) return
    setSearching(true)
    setError(null)
    setAnswer(null)
    try {
      const res = await queryKnowledgeBase(text)
      setAnswer(res)
    } catch (err) {
      setError(errorMessage(err, 'Search failed.'))
    } finally {
      setSearching(false)
    }
  }

  const available = status?.available
  const docs = status?.documents ?? []

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      {/* Left: controls + status */}
      <div className="space-y-5 lg:col-span-2">
        <Card>
          <CardHeader icon={BookOpen} title="Knowledge Base" subtitle="Index medical documents for retrieval-augmented answers" />

          {/* Status */}
          <div className="space-y-2">
            <StatPill icon={Database} label="Vector store" value={status?.vector_backend || '—'} />
            <StatPill icon={Cpu} label="Embeddings" value={status?.embedding_model || '—'} />
            <StatPill icon={Sparkles} label="LLM provider" value={status?.llm_provider || 'offline'} />
            <StatPill icon={Layers} label="Indexed chunks" value={status?.indexed_chunks ?? 0} />
          </div>

          {!available && status && (
            <div className="mt-3 flex items-start gap-2 rounded-xl bg-warning/10 p-3 text-xs text-foreground">
              <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
              <span>
                RAG dependencies not fully available. Install with{' '}
                <code className="rounded bg-surface-2 px-1">pip install sentence-transformers chromadb pypdf</code>.
              </span>
            </div>
          )}

          {/* Actions */}
          <div className="mt-4 flex flex-col gap-2">
            <Button onClick={() => inputRef.current?.click()} loading={uploading} variant="secondary">
              <UploadCloud size={16} /> Upload PDF / TXT / Markdown
            </Button>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.txt,.md,.markdown"
              hidden
              onChange={(e) => onUpload(e.target.files?.[0])}
            />
            <Button onClick={rebuild} loading={indexing}>
              <RefreshCw size={16} /> Rebuild Index
            </Button>
          </div>
          <p className="mt-3 text-xs text-muted">
            Uploaded files are stored in <code className="rounded bg-surface-2 px-1">backend/rag/documents/</code> and indexed automatically.
          </p>
        </Card>

        {/* Document list */}
        <Card>
          <CardHeader icon={FileText} title="Documents" subtitle={`${docs.length} file(s) in the knowledge base`} />
          {docs.length === 0 ? (
            <p className="text-sm text-muted">No documents yet. Upload one to get started.</p>
          ) : (
            <ul className="space-y-1.5">
              {docs.map((d) => (
                <li key={d.name} className="flex items-center justify-between gap-2 rounded-lg bg-surface-2 px-3 py-2">
                  <span className="flex items-center gap-2 truncate text-sm text-foreground">
                    <FileText size={14} className="shrink-0 text-primary" /> {d.name}
                  </span>
                  <Badge tone="neutral">{d.format}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Right: search + answer */}
      <div className="space-y-5 lg:col-span-3">
        <Card>
          <div className="flex items-end gap-2 rounded-2xl border border-border bg-background p-2">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); search() }
              }}
              rows={1}
              placeholder="Ask the knowledge base… e.g. What are the side effects of Ibuprofen?"
              className="max-h-32 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-foreground outline-none placeholder:text-muted"
            />
            <Button onClick={() => search()} loading={searching} disabled={!question.trim()}>
              <Search size={16} /> Search
            </Button>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {['What is Paracetamol used for?', 'Side effects of Ibuprofen', 'Can I take Ibuprofen with Warfarin?'].map((q) => (
              <button
                key={q}
                onClick={() => { setQuestion(q); search(q) }}
                className="rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted transition-colors hover:border-primary/50 hover:text-primary"
              >
                {q}
              </button>
            ))}
          </div>
        </Card>

        {error && (
          <Card className="border-danger/30 bg-danger/5">
            <div className="flex items-start gap-2 text-sm text-foreground">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-danger" />
              <span>{error}</span>
            </div>
          </Card>
        )}

        {searching && (
          <Card className="flex flex-col items-center justify-center gap-3 py-14 text-center">
            <Loader2 size={26} className="animate-spin text-primary" />
            <p className="text-sm text-muted">Retrieving relevant documents and generating an answer…</p>
          </Card>
        )}

        {!searching && !answer && !error && (
          <EmptyState
            icon={Sparkles}
            title="Ask anything about your medical documents"
            description="The assistant searches the vector database, retrieves the most relevant passages, and answers using only that context — with sources and similarity scores."
          />
        )}

        {!searching && answer && (
          <>
            {/* AI answer */}
            <Card>
              <div className="mb-3 flex items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 font-semibold text-foreground">
                  <Sparkles size={18} className="text-primary" /> Answer
                </h3>
                <div className="flex items-center gap-2">
                  <Badge tone="neutral">via {answer.provider}</Badge>
                  <span
                    className="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                    style={{ color: confidenceColor(pct(answer.confidence)), backgroundColor: `${confidenceColor(pct(answer.confidence))}1a` }}
                  >
                    {pct(answer.confidence)}% confidence
                  </span>
                </div>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{answer.answer}</p>

              {answer.sources?.length > 0 && (
                <div className="mt-4 flex flex-wrap items-center gap-1.5">
                  <span className="text-xs font-medium text-muted">Sources:</span>
                  {answer.sources.map((s) => (
                    <Badge key={s} tone="primary"><Quote size={11} /> {s}</Badge>
                  ))}
                </div>
              )}
              {answer.safety_note && (
                <p className="mt-3 text-[11px] text-muted">{answer.safety_note}</p>
              )}
            </Card>

            {/* Retrieved chunks */}
            {answer.chunks?.length > 0 && (
              <Card>
                <CardHeader icon={Layers} title="Retrieved chunks" subtitle="Passages used to ground the answer, with similarity scores" />
                <div className="grid gap-2.5">
                  {answer.chunks.map((c, i) => <ChunkCard key={i} chunk={c} rank={i + 1} />)}
                </div>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  )
}
