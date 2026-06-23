"""Sentence-Transformers embedding layer.

Wraps ``all-MiniLM-L6-v2`` (384-dim, fast, CPU-friendly) behind a tiny, cached
interface. The heavy model is loaded lazily on first use and reused for the
process lifetime, so repeated queries pay the load cost only once.

The model dependency is optional at import time: if ``sentence-transformers`` is
not installed, :meth:`Embedder.available` returns ``False`` and callers degrade
gracefully instead of crashing the application.

Synchronous methods do the CPU-bound encoding; async wrappers offload them to a
thread so FastAPI's event loop stays responsive (Requirement: async wherever
possible).
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from backend.rag.config import config, get_logger

logger = get_logger("rag.embedding")


class Embedder:
    """Lazy, cached wrapper around a SentenceTransformer model."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or config.EMBEDDING_MODEL
        self._model = None
        self._failed = False

    # -- lifecycle ---------------------------------------------------------
    def _load(self):
        if self._model is None and not self._failed:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                logger.info("Loading embedding model '%s'…", self.model_name)
                self._model = SentenceTransformer(self.model_name)
                logger.info("Embedding model ready (dim=%d)", self.dimension)
            except Exception as exc:  # noqa: BLE001
                self._failed = True
                logger.error("Could not load embedding model: %s", exc)
                raise
        return self._model

    def available(self) -> bool:
        """True if the model can be loaded (deps installed, weights reachable)."""
        try:
            return self._load() is not None
        except Exception:  # noqa: BLE001
            return False

    @property
    def dimension(self) -> int:
        model = self._model
        if model is None:
            return 0
        try:
            return int(model.get_sentence_embedding_dimension())
        except Exception:  # noqa: BLE001
            return 0

    # -- encoding (sync) ---------------------------------------------------
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents. Returns one vector per input string."""
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(
            texts,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=True,   # unit vectors -> clean cosine scores
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return self.embed_texts([text])[0]

    # -- encoding (async) --------------------------------------------------
    async def aembed_texts(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_texts, texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.embed_query, text)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Process-wide singleton embedder."""
    return Embedder()
