"""Pure helpers for the Drug Interaction module — no I/O, easy to unit-test.

Kept deliberately small and dependency-light: severity ordering, name
normalisation, and report-summary composition. The service layer imports these
so its own logic stays focused on orchestration.
"""

from __future__ import annotations

import logging

from backend.drug_interactions.schemas import (
    DrugDrugInteraction,
    Severity,
)

logger = logging.getLogger("drug_interactions")


# --------------------------------------------------------------------------
# Severity ordering
# --------------------------------------------------------------------------
# Numeric rank so we can compare / take the max. Higher = more dangerous.
SEVERITY_RANK: dict[Severity, int] = {
    Severity.NONE: 0,
    Severity.LOW: 1,
    Severity.MODERATE: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

# UI tone hint per severity (mirrors the frontend Badge tones; the frontend has
# its own copy too, this is for any server-rendered/exported context).
SEVERITY_TONE: dict[Severity, str] = {
    Severity.NONE: "neutral",
    Severity.LOW: "primary",
    Severity.MODERATE: "warning",
    Severity.HIGH: "danger",
    Severity.CRITICAL: "danger",
}


def coerce_severity(value: str | Severity | None) -> Severity:
    """Best-effort parse of a free-text severity into the enum (defaults NONE)."""
    if isinstance(value, Severity):
        return value
    if not value:
        return Severity.NONE
    try:
        return Severity(str(value).strip().lower())
    except ValueError:
        logger.debug("Unknown severity %r — defaulting to NONE", value)
        return Severity.NONE


def max_severity(severities: list[Severity]) -> Severity:
    """Return the single most dangerous severity in the list (NONE if empty)."""
    if not severities:
        return Severity.NONE
    return max(severities, key=lambda s: SEVERITY_RANK[s])


# --------------------------------------------------------------------------
# Name normalisation
# --------------------------------------------------------------------------
def normalize_name(name: str) -> str:
    """Lowercase, strip dosage/form noise and punctuation for matching.

    Reuses the OCR module's medicine normaliser when importable (single source
    of truth), and falls back to a minimal local version so this module never
    hard-depends on the OCR package.
    """
    try:
        from backend.ocr.medicine_intelligence import normalize as _ocr_normalize

        return _ocr_normalize(name)
    except Exception:  # noqa: BLE001 — OCR module optional from here
        import re

        s = (name or "").lower()
        s = re.sub(r"[^a-z0-9 ]", " ", s)
        return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# Report summary composition
# --------------------------------------------------------------------------
def build_summary(
    interactions: list[DrugDrugInteraction],
    overall: Severity,
    n_medicines: int,
) -> str:
    """Compose a one-line, human-readable headline for the report."""
    if n_medicines < 2:
        return "Add at least two medicines to check for interactions."
    if not interactions:
        return (
            f"No known interactions were found among the {n_medicines} medicines "
            "in the knowledge base. Always confirm with a pharmacist."
        )
    n = len(interactions)
    plural = "interaction" if n == 1 else "interactions"
    return (
        f"Found {n} potential drug {plural}; highest severity: "
        f"{overall.value.upper()}. Review the recommendations below."
    )


def collect_recommendations(
    interactions: list[DrugDrugInteraction],
) -> list[str]:
    """De-duplicate recommendations, surfacing the most severe ones first."""
    seen: set[str] = set()
    ordered: list[str] = []
    for inter in sorted(
        interactions, key=lambda i: SEVERITY_RANK[i.severity], reverse=True
    ):
        rec = inter.recommendation.strip()
        if rec and rec not in seen:
            seen.add(rec)
            ordered.append(rec)
    return ordered


def severity_counts(interactions: list[DrugDrugInteraction]) -> dict[str, int]:
    """Tally interactions per severity level (for badges and summaries)."""
    counts = {s.value: 0 for s in Severity}
    for inter in interactions:
        counts[inter.severity.value] += 1
    return counts
