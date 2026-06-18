"""Confidence scoring + engine selection.

The smartest selection signal for a *medical* prescription isn't raw OCR
confidence — it's how much of the output actually matches real medicine names.
We combine three signals:

* engine self-confidence (mean over lines)
* dictionary agreement (fraction of lines that strongly match a medicine)
* text volume (engines that read more real words usually win ties)
"""

from __future__ import annotations

from backend.ocr.engines.base import EngineResult


def dictionary_agreement(result: EngineResult, index, threshold: float = 78.0) -> float:
    """Fraction of non-trivial lines whose best medicine match >= threshold."""
    candidates = [l.text for l in result.lines if sum(c.isalpha() for c in l.text) >= 3]
    if not candidates:
        return 0.0
    hits = 0
    for text in candidates:
        matches = index.search(text, limit=1)
        if matches and matches[0].score >= threshold:
            hits += 1
    return hits / len(candidates)


def engine_score(result: EngineResult, index) -> float:
    """Overall quality score (0..1) used to rank engines for an image."""
    if not result.available or result.is_empty:
        return 0.0
    agree = dictionary_agreement(result, index)
    conf = result.mean_confidence or 0.5
    # Volume bonus saturates quickly so a verbose-but-wrong engine can't dominate.
    volume = min(len(result.lines) / 8.0, 1.0)
    return round(0.5 * agree + 0.35 * conf + 0.15 * volume, 4)


def select_best(results: list[EngineResult], index) -> tuple[EngineResult, dict]:
    """Pick the best engine result; return it plus a per-engine score table."""
    scored = [(r, engine_score(r, index)) for r in results]
    table = {
        r.engine: {
            "score": s,
            "mean_confidence": round(r.mean_confidence, 3),
            "lines": len(r.lines),
            "available": r.available,
            "error": r.error,
        }
        for r, s in scored
    }
    usable = [(r, s) for r, s in scored if s > 0]
    if not usable:
        # Nothing read anything useful — return the first available (or first).
        fallback = next((r for r in results if r.available), results[0])
        return fallback, table
    best = max(usable, key=lambda x: x[1])[0]
    return best, table
