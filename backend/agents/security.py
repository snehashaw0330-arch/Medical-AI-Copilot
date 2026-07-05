"""Input validation + output sanitisation for the agent layer (Security reqs).

Three concerns, kept in one small, testable place:

* **Input validation** — allowed image types/size for uploads, symptom/medicine
  token cleaning.
* **Output sanitisation** — strip control characters before values are stored or
  returned to the UI.
* **Prompt-injection defence for RAG** — the Knowledge Agent is the only path to
  the knowledge base; before a user-influenced string becomes a retrieval query
  we neutralise instruction-style injections ("ignore previous instructions",
  system/assistant role markers, fenced blocks) and clamp the length.
"""

from __future__ import annotations

import re

_ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
_MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Patterns commonly used to hijack an LLM/RAG prompt.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(above|previous)", re.IGNORECASE),
    re.compile(r"\b(system|assistant|developer)\s*:", re.IGNORECASE),
    re.compile(r"</?(system|instruction|prompt)>", re.IGNORECASE),
    re.compile(r"```.*?```", re.DOTALL),          # fenced blocks
    re.compile(r"\bBEGIN\s+SYSTEM\b", re.IGNORECASE),
]


def sanitize_text(text: str | None, *, max_len: int = 20_000) -> str:
    """Remove control chars and clamp length. Safe for storage / display."""
    if not text:
        return ""
    cleaned = _CONTROL_CHARS.sub(" ", str(text))
    return cleaned.strip()[:max_len]


def sanitize_tokens(items: list[str] | None, *, max_items: int = 50) -> list[str]:
    """Clean a list of short tokens (symptoms / medicine names)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (items or []):
        token = sanitize_text(raw, max_len=120)
        key = token.lower()
        if token and key not in seen:
            seen.add(key)
            out.append(token)
        if len(out) >= max_items:
            break
    return out


def sanitize_rag_query(text: str | None, *, max_len: int = 400) -> str:
    """Neutralise prompt-injection before a string is used as a RAG query."""
    cleaned = sanitize_text(text, max_len=max_len * 3)
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    # Collapse whitespace and clamp to a retrieval-sized query.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len]


def validate_image(filename: str | None, size_bytes: int) -> tuple[bool, str]:
    """Validate an uploaded prescription image. Returns (ok, error_message)."""
    if not filename:
        return False, "No filename provided."
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in _ALLOWED_IMAGE_SUFFIXES:
        return False, f"Unsupported image type '{suffix}'. Allowed: {sorted(_ALLOWED_IMAGE_SUFFIXES)}"
    if size_bytes <= 0:
        return False, "Empty file."
    if size_bytes > _MAX_IMAGE_BYTES:
        return False, "Image exceeds the 15 MB limit."
    return True, ""
