"""Assembles the recommendation for a medicine (pure, synchronous, auditable).

Given a resolved medicine (from :mod:`alternative_finder`) and optional RAG
enrichment, this module builds:

* the structured :class:`DrugInfo` card (Requirement 2),
* the three alternative lists — generic equivalents, brand alternatives and
  similar medicines — each with a plain-language **reason** (Requirement 3),
* a per-medicine AI summary and a confidence score, and
* the overall AI recommendation report narrative.

It contains no I/O and no async; the service supplies dataset + RAG inputs and
persists the result. Keeping the reasoning here makes the "why" auditable in one
place.
"""

from __future__ import annotations

from backend.medicine_recommendation import alternative_finder as af
from backend.medicine_recommendation.schemas import (
    AlternativeKind,
    AlternativeMedicine,
    DrugInfo,
    MedicineRecommendation,
    RelatedDocument,
)
from backend.ocr.medicine_intelligence import normalize

# Default guidance for fields the dataset does not carry (RAG overrides when it
# has something grounded). Clearly generic + cautionary, never fabricated detail.
_DEFAULT_PREGNANCY = (
    "Safety in pregnancy and breastfeeding is not established here — consult your "
    "doctor before use if you are pregnant, planning pregnancy or breastfeeding."
)
_DEFAULT_FOOD = (
    "Follow the label/pharmacist's advice on taking this with food. Many medicines "
    "are gentler on the stomach when taken with or after a meal."
)


# ==========================================================================
# Drug info card
# ==========================================================================
def build_drug_info(resolved: af.ResolvedMedicine, rag_fields: dict | None) -> DrugInfo:
    """Merge dataset structured data with RAG evidence into a DrugInfo card."""
    details = resolved.details or {}
    rag = rag_fields or {}
    form = af.detected_form(resolved.resolved_name)

    substitutes = details.get("substitutes", []) or []
    strengths = af.available_strengths(resolved.resolved_name, *substitutes)
    rx_value, rx_note = af.prescription_required(details, resolved.resolved_name)

    def rag_list(key: str) -> list[str]:
        val = (rag.get(key) or "").strip()
        # RAG fields are short free text; split into bullet-ish lines if present.
        if not val:
            return []
        parts = [p.strip(" -•") for p in val.replace(";", "\n").splitlines()]
        return [p for p in parts if p]

    return DrugInfo(
        generic_name=af.extract_generic(details),
        brand_name=details.get("name", resolved.resolved_name),
        drug_class=details.get("action_class", ""),
        therapeutic_category=details.get("therapeutic_class", ""),
        available_strengths=strengths,
        prescription_required=rx_value,
        prescription_note=rx_note,
        common_uses=details.get("uses", []) or [],
        common_side_effects=details.get("side_effects", []) or [],
        contraindications=rag_list("contraindications"),
        pregnancy_safety=(rag.get("pregnancy_safety") or "").strip() or _DEFAULT_PREGNANCY,
        food_interactions=(rag.get("food_interactions") or "").strip() or _DEFAULT_FOOD,
        storage_instructions=(rag.get("storage") or "").strip() or af.storage_instructions(form),
        habit_forming=details.get("habit_forming", ""),
    )


# ==========================================================================
# Alternatives (with reasons — Requirement 3)
# ==========================================================================
def build_alternatives(
    resolved: af.ResolvedMedicine, max_alternatives: int,
) -> tuple[list[AlternativeMedicine], list[AlternativeMedicine], list[AlternativeMedicine]]:
    """Return (generic_equivalents, brand_alternatives, similar_medicines)."""
    details = resolved.details or {}
    substitutes = [s for s in (details.get("substitutes", []) or []) if s]
    therapeutic = details.get("therapeutic_class") or None

    # Substitutes from the dataset are direct, same-composition swaps. We surface
    # the first as the "generic equivalent" candidate and the rest as brand
    # alternatives — all are clinically equivalent switches per the dataset.
    generics: list[AlternativeMedicine] = []
    brands: list[AlternativeMedicine] = []
    exclude = {normalize(resolved.resolved_name)}
    for i, sub in enumerate(substitutes[:max_alternatives]):
        exclude.add(normalize(sub))
        alt = AlternativeMedicine(
            name=sub,
            kind=AlternativeKind.BRAND_ALTERNATIVE,
            match_score=95.0 - i * 3,
            therapeutic_category=therapeutic,
            reason=("Listed in the dataset as a direct substitute — same "
                    "composition/strength, so it can usually be swapped in on a "
                    "pharmacist's advice."),
        )
        brands.append(alt)

    # Present the top substitute additionally as the generic-equivalent option,
    # since substitutes share the active composition (often a cheaper generic).
    if substitutes:
        top = substitutes[0]
        generics.append(AlternativeMedicine(
            name=top,
            kind=AlternativeKind.GENERIC_EQUIVALENT,
            match_score=96.0,
            therapeutic_category=therapeutic,
            reason=("Shares the same active composition as the detected medicine, "
                    "so it is an equivalent option — generics are typically more "
                    "affordable at the same efficacy."),
        ))

    # Similar medicines: same therapeutic class (different composition).
    similar: list[AlternativeMedicine] = []
    for name, relevance in af.find_similar(details, resolved.resolved_name, exclude, max_alternatives):
        similar.append(AlternativeMedicine(
            name=name,
            kind=AlternativeKind.SIMILAR,
            match_score=relevance,
            therapeutic_category=therapeutic,
            reason=(f"Belongs to the same therapeutic category"
                    + (f" ('{therapeutic}')" if therapeutic else "")
                    + " — used for similar conditions, though the exact molecule "
                    "differs. Only switch on medical advice."),
        ))

    return generics, brands, similar


# ==========================================================================
# Warnings, confidence, summary
# ==========================================================================
def build_warnings(info: DrugInfo) -> list[str]:
    """Surface the most important safety flags for the medicine."""
    warnings: list[str] = []
    if (info.habit_forming or "").strip().lower() == "yes":
        warnings.append("This medicine can be habit-forming — use strictly as prescribed.")
    if info.prescription_required == "yes":
        warnings.append("Prescription medicine — do not self-medicate or share it.")
    if info.contraindications:
        warnings.append("Has documented contraindications — review them before use.")
    return warnings


def compute_confidence(
    resolved: af.ResolvedMedicine, info: DrugInfo, rag_confidence: float,
) -> float:
    """0..100 confidence combining resolution, data completeness and RAG."""
    if not resolved.matched:
        return round(min(35.0, resolved.score), 1)
    # Completeness: how many of the key fields we actually filled.
    filled = sum(bool(x) for x in [
        info.common_uses, info.common_side_effects, info.drug_class,
        info.therapeutic_category, info.available_strengths,
    ])
    completeness = filled / 5.0
    score = 0.55 * resolved.score + 0.30 * (completeness * 100) + 0.15 * (rag_confidence * 100)
    return round(max(0.0, min(100.0, score)), 1)


def build_summary(
    resolved: af.ResolvedMedicine,
    info: DrugInfo,
    generics: list[AlternativeMedicine],
    brands: list[AlternativeMedicine],
    similar: list[AlternativeMedicine],
    rag_summary: str | None,
) -> str:
    """Per-medicine narrative (dataset-grounded, RAG appended when available)."""
    if not resolved.matched:
        return (f"'{resolved.detected}' could not be confidently matched to a known "
                "medicine, so information may be incomplete. Please verify the name.")
    bits: list[str] = []
    name = info.brand_name or resolved.resolved_name
    if info.common_uses:
        bits.append(f"{name} is commonly used for {', '.join(info.common_uses[:2]).lower()}.")
    if info.therapeutic_category:
        bits.append(f"It belongs to the {info.therapeutic_category.title()} category.")
    n_alt = len(brands)
    if n_alt:
        bits.append(f"{n_alt} substitute brand(s) and "
                    f"{len(similar)} similar-class medicine(s) were found as options.")
    if generics:
        bits.append("A generic-equivalent option is available and is usually more affordable.")
    narrative = " ".join(bits) or f"{name} was identified in the medicine dataset."
    if rag_summary:
        narrative += "\n\nFrom the knowledge base: " + rag_summary.strip()
    return narrative


def to_related_documents(chunks: list[dict], limit: int = 4) -> list[RelatedDocument]:
    """Map RAG chunks to the RelatedDocument contract."""
    docs: list[RelatedDocument] = []
    for c in (chunks or [])[:limit]:
        docs.append(RelatedDocument(
            source=c.get("source", "knowledge-base"),
            excerpt=(c.get("text", "") or "")[:400],
            score=float(c.get("score", 0.0) or 0.0),
        ))
    return docs


# ==========================================================================
# Overall AI recommendation report (Requirement 3)
# ==========================================================================
def build_ai_report(recommendations: list[MedicineRecommendation]) -> str:
    """A short narrative explaining the alternatives across all medicines."""
    if not recommendations:
        return "No medicines were provided to analyse."
    lines: list[str] = []
    matched = [r for r in recommendations if r.matched]
    lines.append(
        f"Analysed {len(recommendations)} medicine(s); "
        f"{len(matched)} were confidently identified."
    )
    for r in recommendations:
        if not r.matched:
            lines.append(f"• {r.detected_name}: not confidently identified — verify the name.")
            continue
        parts: list[str] = []
        if r.generic_equivalents:
            parts.append(f"a generic equivalent ({r.generic_equivalents[0].name})")
        if r.brand_alternatives:
            parts.append(f"{len(r.brand_alternatives)} substitute brand(s)")
        if r.similar_medicines:
            parts.append(f"{len(r.similar_medicines)} similar-class option(s)")
        detail = "; ".join(parts) if parts else "no alternatives were found in the dataset"
        lines.append(f"• {r.resolved_name}: {detail}. "
                     "Alternatives are suggested because they share the same "
                     "composition (substitutes/generics) or therapeutic category "
                     "(similar medicines). Any switch needs a doctor/pharmacist's approval.")
    return "\n".join(lines)
