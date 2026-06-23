"""Retriever — ties the embedder and the vector store together.

Responsibilities:

* **Indexing** — embed document chunks and upsert them into the vector store.
* **Retrieval** — embed a query, search the store, filter weak matches.

This is the only place that knows *both* the embedder and the store exist, so
it is the natural seam for swapping either one independently.
"""

from __future__ import annotations

from backend.rag.config import config, get_logger
from backend.rag.document_loader import DocumentChunk, load_chunks
from backend.rag.embedding import get_embedder
from backend.rag.vector_store import RetrievedChunk, get_vector_store

logger = get_logger("rag.retriever")


class Retriever:
    """Indexing + similarity search over the medical knowledge base."""

    def __init__(self) -> None:
        self.embedder = get_embedder()
        self.store = get_vector_store()

    # -- readiness ---------------------------------------------------------
    def available(self) -> bool:
        """True only if BOTH the embedder and the vector store are usable."""
        return self.embedder.available() and self.store.available()

    def count(self) -> int:
        return self.store.count()

    # -- indexing ----------------------------------------------------------
    def index_chunks(self, chunks: list[DocumentChunk], *, reset: bool = True) -> int:
        """Embed and store the given chunks. Returns the number indexed."""
        if not chunks:
            logger.warning("No chunks to index.")
            return 0
        if reset:
            self.store.reset()

        texts = [c.text for c in chunks]
        logger.info("Embedding %d chunks…", len(texts))
        embeddings = self.embedder.embed_texts(texts)
        self.store.add(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=texts,
            metadatas=[c.metadata for c in chunks],
        )
        logger.info("Indexed %d chunks (collection size=%d)", len(chunks), self.store.count())
        return len(chunks)

    def reindex_from_disk(self, directory=None, *, reset: bool = True) -> int:
        """Reload every document from disk and rebuild the index."""
        chunks = load_chunks(directory)
        return self.index_chunks(chunks, reset=reset)

    # -- retrieval ---------------------------------------------------------
    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        min_similarity: float | None = None,
    ) -> list[RetrievedChunk]:
        """Return the most relevant chunks for ``query`` (strongest first)."""
        if not query.strip():
            return []
        top_k = top_k or config.TOP_K
        threshold = config.MIN_SIMILARITY if min_similarity is None else min_similarity

        embedding = self.embedder.embed_query(query)
        hits = self.store.query(embedding, top_k=top_k)
        filtered = [h for h in hits if h.score >= threshold]
        # If everything was filtered out but we did get hits, keep the best one
        # so the caller still has *some* context to work with.
        if not filtered and hits:
            filtered = hits[:1]
        return filtered


# Module-level singleton so the model/store load once.
_RETRIEVER: Retriever | None = None


def get_retriever() -> Retriever:
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = Retriever()
    return _RETRIEVER
