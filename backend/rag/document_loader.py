"""Load and chunk medical knowledge documents for indexing.

Supported formats (auto-detected by extension):

* ``.txt``             — plain text
* ``.md`` / ``.markdown`` — markdown (read as text; structure preserved)
* ``.pdf``             — extracted page-by-page via :mod:`pypdf` (lazy import)

Each document is split into overlapping character windows ("chunks"). Overlap
preserves context that would otherwise be cut mid-sentence between windows.
Splitting prefers paragraph / sentence boundaries so chunks stay readable.

The loader is dependency-light: only PDF parsing needs an optional package, and
its absence degrades to "skip PDFs with a warning" rather than crashing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.rag.config import config, get_logger

logger = get_logger("rag.loader")


@dataclass
class DocumentChunk:
    """One indexable passage of a source document."""

    id: str
    text: str
    source: str                       # file name
    metadata: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Reading individual files
# --------------------------------------------------------------------------
def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:  # noqa: BLE001
        logger.warning("pypdf not installed — skipping PDF %s (pip install pypdf)", path.name)
        return ""
    try:
        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n\n".join(pages)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to read PDF %s: %s", path.name, exc)
        return ""


def read_document(path: Path) -> str:
    """Return the raw text of a single document, or "" if unreadable."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix in {".txt", ".md", ".markdown"}:
        return _read_text(path)
    return ""


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------
_WHITESPACE = re.compile(r"[ \t]+")
_MULTINEWLINE = re.compile(r"\n{3,}")


def _normalize(text: str) -> str:
    text = _WHITESPACE.sub(" ", text)
    text = _MULTINEWLINE.sub("\n\n", text)
    return text.strip()


def chunk_text(
    text: str,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split text into overlapping windows, preferring natural boundaries.

    We walk the text in steps of ``chunk_size - overlap``; for each window we
    back off to the nearest paragraph/sentence/space boundary so a chunk never
    ends mid-word. Empty windows are skipped.
    """
    chunk_size = chunk_size or config.CHUNK_SIZE
    overlap = overlap or config.CHUNK_OVERLAP
    text = _normalize(text)
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Prefer to cut on a paragraph break, then sentence, then space.
            window = text[start:end]
            for sep in ("\n\n", ". ", "\n", " "):
                cut = window.rfind(sep)
                if cut > chunk_size * 0.5:  # only back off if we keep enough text
                    end = start + cut + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += step
    return chunks


def _chunk_id(source: str, index: int, text: str) -> str:
    digest = hashlib.sha1(f"{source}:{index}:{text}".encode("utf-8")).hexdigest()[:16]
    return f"{Path(source).stem}-{index}-{digest}"


# --------------------------------------------------------------------------
# Folder-level loading
# --------------------------------------------------------------------------
def discover_documents(directory: str | Path | None = None) -> list[Path]:
    """Recursively list every supported document under ``directory``."""
    root = Path(directory or config.DOCUMENTS_DIR)
    if not root.exists():
        return []
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in config.SUPPORTED_EXTENSIONS
    )


def load_chunks(directory: str | Path | None = None) -> list[DocumentChunk]:
    """Load every supported document and return all chunks ready for indexing."""
    paths = discover_documents(directory)
    chunks: list[DocumentChunk] = []
    for path in paths:
        raw = read_document(path)
        if not raw.strip():
            logger.warning("No extractable text in %s — skipped", path.name)
            continue
        pieces = chunk_text(raw)
        for i, piece in enumerate(pieces):
            chunks.append(
                DocumentChunk(
                    id=_chunk_id(path.name, i, piece),
                    text=piece,
                    source=path.name,
                    metadata={
                        "source": path.name,
                        "path": str(path),
                        "chunk_index": i,
                        "format": path.suffix.lower().lstrip("."),
                    },
                )
            )
    logger.info("Loaded %d chunks from %d documents", len(chunks), len(paths))
    return chunks


def document_summary(directory: str | Path | None = None) -> list[dict]:
    """Lightweight listing of documents (name, format, size) for the UI/status."""
    out = []
    for path in discover_documents(directory):
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        out.append(
            {"name": path.name, "format": path.suffix.lower().lstrip("."), "size_bytes": size}
        )
    return out
