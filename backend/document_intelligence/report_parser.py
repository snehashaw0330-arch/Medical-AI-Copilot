"""Text extraction dispatch (step 3) + narrative-document section parsing (step 4).

Images are OCR'd via ``backend.ocr.pipeline.extract_raw_text`` (the same
recognition engines/providers the prescription pipeline uses). PDFs are read
directly with ``pypdf`` (already a hard dependency — see
``backend/rag/document_loader.py`` for the identical lazy-import pattern);
when a PDF turns out to be a scanned image with no extractable text, we
optionally rasterize page one with ``pymupdf`` (a new *optional* dependency,
degrading gracefully with an actionable warning when it isn't installed) and
OCR that instead.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from backend.config import settings
from backend.document_intelligence.schemas import DocumentFields, DocumentType
from backend.ocr.pipeline import extract_raw_text

logger = logging.getLogger("document_intelligence")

_MIN_PDF_TEXT_CHARS = 40


def _read_pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:  # noqa: BLE001
        logger.warning("pypdf not installed — cannot read PDF text from %s", path)
        return ""
    try:
        reader = PdfReader(path)
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n\n".join(pages).strip()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read PDF text from %s", path)
        return ""


def _rasterize_pdf_page(path: str, page_index: int = 0) -> str | None:
    """Render one PDF page to a PNG for OCR. Returns the PNG path, or None."""
    try:
        import fitz  # type: ignore  # pymupdf
    except Exception:  # noqa: BLE001
        logger.warning(
            "pymupdf not installed — cannot OCR scanned PDF %s "
            "(pip install pymupdf, or upload the page as an image instead)",
            path,
        )
        return None
    try:
        doc = fitz.open(path)
        page = doc.load_page(page_index)
        pix = page.get_pixmap(dpi=300)
        dest = Path(settings.UPLOAD_DIR) / f"{uuid.uuid4().hex}.png"
        pix.save(str(dest))
        doc.close()
        return str(dest)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to rasterize PDF %s", path)
        return None


def extract_text(
    path: str, suffix: str, provider_name: str | None = None
) -> dict:
    """Extract raw text from an uploaded document. Returns
    ``{"raw_text": str, "method": str, "engine": str | None, "warnings": list[str]}``.
    Never raises — extraction failures degrade to an empty result with a
    warning so the analysis pipeline can still respond.
    """
    warnings: list[str] = []
    suffix = suffix.lower()

    if suffix == ".pdf":
        text = _read_pdf_text(path)
        if len(text.strip()) >= _MIN_PDF_TEXT_CHARS:
            return {"raw_text": text, "method": "pdf-text", "engine": "pypdf", "warnings": warnings}

        raster_path = _rasterize_pdf_page(path)
        if raster_path is None:
            warnings.append(
                "This looks like a scanned PDF with no extractable text, and "
                "OCR-on-PDF support (pymupdf) isn't installed. Try uploading "
                "a page image (JPG/PNG) instead."
            )
            return {"raw_text": text, "method": "pdf-text", "engine": "pypdf", "warnings": warnings}
        try:
            ocr_text, _engine_table, engine = extract_raw_text(raster_path, provider_name)
            return {"raw_text": ocr_text, "method": "pdf-ocr", "engine": engine, "warnings": warnings}
        finally:
            Path(raster_path).unlink(missing_ok=True)

    # Image formats — reuse the existing OCR recognition engines/providers.
    ocr_text, _engine_table, engine = extract_raw_text(path, provider_name)
    return {"raw_text": ocr_text, "method": "ocr", "engine": engine, "warnings": warnings}


# --------------------------------------------------------------------------
# Narrative section parsing (Discharge Summary, Medical Certificate,
# Handwritten Prescription treated generically here — the OCR-specific
# medicine-level parsing for prescriptions still lives in backend/ocr/).
# --------------------------------------------------------------------------
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s*(.+?)\s*#*\s*$")
_BOLD_HEADING_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*:?\s*$")
_COLON_HEADING_RE = re.compile(r"^\s*([A-Za-z][A-Za-z /&()-]{2,45}):\s*(.*)$")

_COMMON_FIELD_ALIASES: dict[str, list[str]] = {
    "patient_name": ["patient name", "name", "patient"],
    "age": ["age"],
    "gender": ["gender", "sex"],
    "date": ["date", "date of issue", "report date"],
    "doctor": ["doctor", "physician", "consultant", "referring doctor", "attending physician"],
    "hospital": ["hospital", "clinic", "hospital name"],
}


def _match_common_field(heading: str) -> str | None:
    h = heading.strip().lower()
    for field, names in _COMMON_FIELD_ALIASES.items():
        if any(h == n or h.startswith(n) for n in names):
            return field
    return None


def parse_structured_sections(raw_text: str, document_type: DocumentType) -> DocumentFields:
    """Best-effort heading/label detection into common fields + a section catch-all.

    Recognises ``# Heading``, ``**Heading**`` and ``Label: value`` styles —
    the same heuristic already proven for offline RAG field extraction
    (``backend/rag/rag_service.py::extract_structured_fields``), generalized
    to arbitrary document sections instead of a fixed medicine-field set.
    """
    common: dict[str, str] = {}
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in raw_text.splitlines():
        heading = None
        inline = None
        m = _HEADING_RE.match(line)
        if m:
            heading = m.group(2)
        else:
            m = _BOLD_HEADING_RE.match(line)
            if m:
                heading = m.group(1)
            else:
                m = _COLON_HEADING_RE.match(line)
                if m:
                    heading = m.group(1)
                    inline = m.group(2)

        if heading is not None:
            common_field = _match_common_field(heading)
            if common_field:
                if inline and inline.strip():
                    common[common_field] = inline.strip()
                current = None
                continue
            current = heading.strip()
            if current and inline and inline.strip():
                sections.setdefault(current, []).append(inline.strip())
            continue

        if current and line.strip():
            sections.setdefault(current, []).append(line.strip())

    return DocumentFields(
        **common,
        sections={k: " ".join(v).strip() for k, v in sections.items() if v},
    )
