"""Central configuration for the RAG subsystem.

All values are environment-overridable so the same code runs locally (offline,
no API keys) and in production (with a cloud LLM). Sensible defaults make the
system fully functional out of the box with **zero** configuration.

Reuses the application-wide ``ROOT_DIR`` and cloud API keys from
:mod:`backend.config` so there is a single source of truth for credentials.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from backend.config import ROOT_DIR, settings as app_settings


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class RAGConfig:
    """Runtime settings for retrieval + generation. Instantiated once below."""

    # --- Storage paths ----------------------------------------------------
    # Folder watched for knowledge documents (txt / pdf / md). Auto-created.
    DOCUMENTS_DIR: Path = Path(
        os.getenv("RAG_DOCUMENTS_DIR", str(Path(__file__).resolve().parent / "documents"))
    )
    # Where the vector database persists its index between runs.
    PERSIST_DIR: Path = Path(
        os.getenv("RAG_PERSIST_DIR", str(Path(__file__).resolve().parent / "vector_store"))
    )

    # --- Embeddings -------------------------------------------------------
    EMBEDDING_MODEL: str = os.getenv("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # --- Vector store -----------------------------------------------------
    # "chroma" (preferred) or "faiss". The factory in vector_store.py picks the
    # implementation; adding a new backend means adding one class, no edits here.
    VECTOR_BACKEND: str = os.getenv("RAG_VECTOR_BACKEND", "chroma").lower()
    COLLECTION_NAME: str = os.getenv("RAG_COLLECTION", "medical_knowledge")
    # Cosine distance keeps scores intuitive: similarity = 1 - distance.
    DISTANCE_METRIC: str = os.getenv("RAG_DISTANCE_METRIC", "cosine")

    # --- Chunking ---------------------------------------------------------
    CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "900"))        # chars
    CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))  # chars

    # --- Retrieval --------------------------------------------------------
    TOP_K: int = int(os.getenv("RAG_TOP_K", "4"))
    # Chunks below this similarity (0..1) are dropped as irrelevant.
    MIN_SIMILARITY: float = float(os.getenv("RAG_MIN_SIMILARITY", "0.2"))

    # --- Generation (LLM) -------------------------------------------------
    # "auto"   -> OpenAI if OPENAI_API_KEY, else Gemini if GEMINI_API_KEY,
    #             else "offline" (extractive answers from retrieved context).
    # "openai" | "gemini" | "offline" force a specific path.
    LLM_PROVIDER: str = os.getenv("RAG_LLM_PROVIDER", "auto").lower()
    LLM_TEMPERATURE: float = float(os.getenv("RAG_LLM_TEMPERATURE", "0.2"))
    LLM_MAX_TOKENS: int = int(os.getenv("RAG_LLM_MAX_TOKENS", "800"))

    # Reused from the app-wide settings (single source of truth).
    OPENAI_API_KEY: str | None = app_settings.OPENAI_API_KEY
    OPENAI_MODEL: str = os.getenv("RAG_OPENAI_MODEL", app_settings.OPENAI_MODEL)
    GEMINI_API_KEY: str | None = app_settings.GEMINI_API_KEY
    GEMINI_MODEL: str = os.getenv("RAG_GEMINI_MODEL", app_settings.GEMINI_MODEL)

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".txt", ".md", ".markdown", ".pdf"})

    def resolved_llm_provider(self) -> str:
        """Collapse "auto" to a concrete provider based on available keys."""
        if self.LLM_PROVIDER == "auto":
            if self.OPENAI_API_KEY:
                return "openai"
            if self.GEMINI_API_KEY:
                return "gemini"
            return "offline"
        return self.LLM_PROVIDER


config = RAGConfig()

# Ensure storage folders exist at import time (never fatal).
for _dir in (config.DOCUMENTS_DIR, config.PERSIST_DIR):
    try:
        Path(_dir).mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# Logging — one configured logger for the whole subsystem.
# --------------------------------------------------------------------------
def get_logger(name: str = "rag") -> logging.Logger:
    """Return a module logger with a sane default handler (configured once)."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(os.getenv("RAG_LOG_LEVEL", "INFO").upper())
        logger.propagate = False
    return logger
