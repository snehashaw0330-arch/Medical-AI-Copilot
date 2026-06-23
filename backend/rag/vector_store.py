"""Vector database abstraction + ChromaDB implementation.

A thin, swappable interface (:class:`VectorStore`) sits in front of the concrete
database so the rest of the RAG code never imports ChromaDB directly. Adding a
new backend (FAISS, Qdrant, pgvector, …) means writing one subclass and
registering it in :func:`get_vector_store` — nothing else changes
(Requirement: easy future extension).

ChromaDB is the default/preferred store: it persists to disk, needs no server,
and stores documents + metadata + embeddings together. We configure the
collection for **cosine** distance so similarity scores are simply
``1 - distance`` in ``[0, 1]``.

All ChromaDB imports are lazy; if the package is missing, :meth:`available`
returns ``False`` and the API surfaces a clean "not installed" message.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.rag.config import config, get_logger

logger = get_logger("rag.vector_store")


@dataclass
class RetrievedChunk:
    """A single search hit returned from the vector store."""

    text: str
    source: str
    score: float                  # similarity in 0..1 (higher = more relevant)
    metadata: dict


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------
class VectorStore:
    """Backend-agnostic vector store contract."""

    backend: str = "base"

    def available(self) -> bool:                       # pragma: no cover
        raise NotImplementedError

    def add(self, ids, embeddings, documents, metadatas) -> None:  # pragma: no cover
        raise NotImplementedError

    def query(self, embedding, top_k: int) -> list[RetrievedChunk]:  # pragma: no cover
        raise NotImplementedError

    def count(self) -> int:                            # pragma: no cover
        raise NotImplementedError

    def reset(self) -> None:                           # pragma: no cover
        raise NotImplementedError

    def sources(self) -> list[str]:                    # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------
# ChromaDB implementation
# --------------------------------------------------------------------------
class ChromaVectorStore(VectorStore):
    backend = "chroma"

    def __init__(self) -> None:
        self._client = None
        self._collection = None
        self._failed = False

    def _get_collection(self):
        if self._collection is None and not self._failed:
            try:
                import chromadb  # type: ignore
                from chromadb.config import Settings  # type: ignore

                self._client = chromadb.PersistentClient(
                    path=str(config.PERSIST_DIR),
                    settings=Settings(anonymized_telemetry=False, allow_reset=True),
                )
                # We supply our own embeddings, so no embedding_function here.
                self._collection = self._client.get_or_create_collection(
                    name=config.COLLECTION_NAME,
                    metadata={"hnsw:space": config.DISTANCE_METRIC},
                )
                logger.info(
                    "Chroma collection '%s' ready at %s",
                    config.COLLECTION_NAME, config.PERSIST_DIR,
                )
            except Exception as exc:  # noqa: BLE001
                self._failed = True
                logger.error("ChromaDB unavailable: %s", exc)
                raise
        return self._collection

    # -- contract ----------------------------------------------------------
    def available(self) -> bool:
        try:
            return self._get_collection() is not None
        except Exception:  # noqa: BLE001
            return False

    def add(self, ids, embeddings, documents, metadatas) -> None:
        collection = self._get_collection()
        # Upsert so re-indexing the same chunk id is idempotent.
        collection.upsert(
            ids=list(ids),
            embeddings=list(embeddings),
            documents=list(documents),
            metadatas=list(metadatas),
        )

    def query(self, embedding, top_k: int) -> list[RetrievedChunk]:
        collection = self._get_collection()
        if collection.count() == 0:
            return []
        res = collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        hits: list[RetrievedChunk] = []
        for doc, meta, dist in zip(docs, metas, dists):
            # Cosine distance -> similarity. Clamp into [0, 1].
            similarity = max(0.0, min(1.0, 1.0 - float(dist)))
            meta = meta or {}
            hits.append(
                RetrievedChunk(
                    text=doc or "",
                    source=str(meta.get("source", "unknown")),
                    score=round(similarity, 4),
                    metadata=meta,
                )
            )
        return hits

    def count(self) -> int:
        try:
            return self._get_collection().count()
        except Exception:  # noqa: BLE001
            return 0

    def reset(self) -> None:
        """Drop and recreate the collection (used before a full re-index)."""
        collection = self._get_collection()
        try:
            self._client.delete_collection(config.COLLECTION_NAME)
        except Exception:  # noqa: BLE001
            pass
        self._collection = self._client.get_or_create_collection(
            name=config.COLLECTION_NAME,
            metadata={"hnsw:space": config.DISTANCE_METRIC},
        )

    def sources(self) -> list[str]:
        try:
            collection = self._get_collection()
            data = collection.get(include=["metadatas"])
            seen = {str((m or {}).get("source", "unknown")) for m in data.get("metadatas", [])}
            return sorted(seen)
        except Exception:  # noqa: BLE001
            return []


# --------------------------------------------------------------------------
# Factory (registry) — add a backend here, nothing else changes.
# --------------------------------------------------------------------------
_REGISTRY: dict[str, type[VectorStore]] = {
    "chroma": ChromaVectorStore,
}

_INSTANCE: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Return the configured vector-store singleton."""
    global _INSTANCE
    if _INSTANCE is None:
        cls = _REGISTRY.get(config.VECTOR_BACKEND)
        if cls is None:
            raise RuntimeError(
                f"Unknown RAG_VECTOR_BACKEND '{config.VECTOR_BACKEND}'. "
                f"Available: {sorted(_REGISTRY)}. "
                "Register a new VectorStore subclass in vector_store.py to add one."
            )
        _INSTANCE = cls()
    return _INSTANCE
