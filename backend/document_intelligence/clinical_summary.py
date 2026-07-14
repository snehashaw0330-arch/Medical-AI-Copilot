"""RAG-grounded clinical summary + AI explanation (steps 5-8 of the workflow).

Retrieves relevant medical knowledge for the document via
``backend.rag.retriever`` (best-effort, non-fatal — same contract every other
module already uses), then generates the narrative summary and explanation
via the provider-agnostic ``backend.llm`` layer. "Possible clinical meaning"
per abnormal finding and follow-up suggestions are composed deterministically
from a rule table so they are always present and reviewable even with no LLM
configured (the offline-safe guarantee ``backend/llm`` already provides).
"""

from __future__ import annotations

import logging
import re

from backend.config import settings
from backend.document_intelligence.schemas import (
    ClinicalSummary,
    DocumentFields,
    DocumentType,
    LabReportAnalysis,
    PossibleMeaning,
)
from backend.rag.prompts import SAFETY_FOOTER, format_context

logger = logging.getLogger("document_intelligence")

# --------------------------------------------------------------------------
# Deterministic "possible clinical meaning" per test + direction. Generic
# fallback is used for anything not explicitly listed here.
# --------------------------------------------------------------------------
_MEANINGS: dict[str, dict[str, str]] = {
    "Hemoglobin": {
        "low": "May indicate anemia (iron/vitamin deficiency, chronic disease, or blood loss).",
        "high": "May indicate polycythemia, dehydration, or a chronic lung/heart condition.",
    },
    "WBC Count": {
        "high": "May indicate infection, inflammation, or a reactive/leukemoid response.",
        "low": "May indicate bone-marrow suppression, viral infection, or an autoimmune process.",
    },
    "Platelet Count": {
        "low": "May indicate thrombocytopenia (bleeding risk) — dengue, viral infection, or marrow disorders.",
        "high": "May indicate a reactive process, inflammation, or a myeloproliferative disorder.",
    },
    "SGOT": {"high": "May indicate liver cell injury (hepatitis, fatty liver, or drug-induced)."},
    "SGPT": {"high": "May indicate liver cell injury (hepatitis, fatty liver, or drug-induced)."},
    "Total Bilirubin": {"high": "May indicate liver dysfunction, bile-duct obstruction, or hemolysis."},
    "Alkaline Phosphatase": {"high": "May indicate bile-duct obstruction, liver disease, or bone turnover."},
    "Blood Urea": {"high": "May indicate reduced kidney function or dehydration."},
    "Serum Creatinine": {"high": "May indicate reduced kidney function (renal impairment)."},
    "eGFR": {"low": "May indicate reduced kidney filtration function."},
    "Uric Acid": {"high": "May indicate risk of gout or reduced kidney clearance."},
    "TSH": {
        "high": "May indicate hypothyroidism (underactive thyroid).",
        "low": "May indicate hyperthyroidism (overactive thyroid).",
    },
    "Total Cholesterol": {"high": "May indicate increased cardiovascular risk."},
    "LDL Cholesterol": {"high": "May indicate increased cardiovascular risk ('bad' cholesterol elevated)."},
    "HDL Cholesterol": {"low": "Lower 'protective' cholesterol — may increase cardiovascular risk."},
    "Triglycerides": {"high": "May indicate metabolic risk, poor diet control, or uncontrolled diabetes."},
    "Sodium": {"low": "May indicate hyponatremia.", "high": "May indicate dehydration or hypernatremia."},
    "Potassium": {"low": "May indicate hypokalemia.", "high": "May indicate hyperkalemia — needs prompt review."},
}

_FOLLOW_UPS: dict[str, str] = {
    "cbc": "Consider a repeat CBC and clinical correlation; consult a physician if symptoms persist.",
    "lft": "Consider a repeat Liver Function Test and hepatology review if abnormalities persist.",
    "kft": "Consider a repeat Kidney Function Test and nephrology review if abnormalities persist.",
    "lipid": "Consider lifestyle modification (diet/exercise) and cardiology review for persistently high lipids.",
    "thyroid": "Consider endocrinology review to evaluate thyroid function further.",
    "generic": "Discuss these results with your treating physician before making any treatment decisions.",
}

_CATEGORY_BY_TYPE: dict[DocumentType, str] = {
    DocumentType.CBC_REPORT: "cbc",
    DocumentType.LFT_REPORT: "lft",
    DocumentType.KFT_REPORT: "kft",
    DocumentType.LIPID_PROFILE: "lipid",
    DocumentType.THYROID_REPORT: "thyroid",
}

_SYSTEM_PROMPT = (
    "You are MediSense, a careful medical document assistant. Summarise the "
    "provided document using ONLY the retrieved context and the structured "
    "findings given to you. Never invent facts, diagnoses, or values. Be "
    "concise, plain-language, and always frame findings as informational, "
    "not a diagnosis. Respond in exactly two labeled sections: "
    "'Summary:' followed by a short overall summary, then 'Explanation:' "
    "followed by a plain-language explanation of what the abnormal findings "
    "could mean and why they matter."
)


def _build_query(document_type: DocumentType, fields: DocumentFields, lab_analysis: LabReportAnalysis | None) -> str:
    parts = [document_type.value.replace("_", " ")]
    if lab_analysis:
        parts += [r.test_name for r in lab_analysis.results if r.status in {"high", "low"}]
    if fields.sections.get("Diagnosis"):
        parts.append(fields.sections["Diagnosis"])
    return " ".join(parts) or document_type.value


def _deterministic_meanings(lab_analysis: LabReportAnalysis | None) -> list[PossibleMeaning]:
    if not lab_analysis:
        return []
    out: list[PossibleMeaning] = []
    for r in lab_analysis.results:
        if r.status not in {"high", "low"}:
            continue
        meaning = _MEANINGS.get(r.test_name, {}).get(
            r.status, "This value is outside the typical reference range — clinical correlation advised."
        )
        out.append(PossibleMeaning(finding=f"{r.test_name} is {r.status}", meaning=meaning))
    return out


def _deterministic_follow_ups(document_type: DocumentType, lab_analysis: LabReportAnalysis | None) -> list[str]:
    if not lab_analysis or lab_analysis.abnormal_count == 0:
        return []
    category = _CATEGORY_BY_TYPE.get(document_type, "generic")
    suggestions = [_FOLLOW_UPS.get(category, _FOLLOW_UPS["generic"])]
    if category != "generic":
        suggestions.append(_FOLLOW_UPS["generic"])
    return suggestions


def _abnormal_finding_strings(lab_analysis: LabReportAnalysis | None) -> list[str]:
    if not lab_analysis:
        return []
    return [
        f"{r.test_name}: {r.value} {r.unit or ''} ({r.status.upper()}, reference {r.reference_range or 'n/a'})".strip()
        for r in lab_analysis.results
        if r.status in {"high", "low"}
    ]


_SECTION_RE = re.compile(r"summary\s*:\s*(?P<summary>.*?)\s*explanation\s*:\s*(?P<explanation>.*)", re.IGNORECASE | re.DOTALL)


def _split_llm_response(text: str) -> tuple[str, str, bool]:
    """Returns (summary, explanation, matched). ``matched`` is False when the
    model didn't follow the two-section format (e.g. the offline extractive
    provider, which just echoes prompt text) — callers should keep their
    deterministic text in that case rather than use the raw echo."""
    m = _SECTION_RE.search(text)
    if m:
        return m.group("summary").strip(), m.group("explanation").strip(), True
    return text.strip(), "", False


def _offline_summary(document_type: DocumentType, lab_analysis: LabReportAnalysis | None) -> str:
    label = document_type.value.replace("_", " ").title()
    if lab_analysis and lab_analysis.total_count:
        return (
            f"{label} analyzed: {lab_analysis.total_count} test(s) detected, "
            f"{lab_analysis.abnormal_count} outside the reference range."
        )
    return f"{label} analyzed. No structured lab values were detected in this document."


async def generate_summary(
    document_type: DocumentType,
    fields: DocumentFields,
    lab_analysis: LabReportAnalysis | None,
    raw_text: str,
) -> ClinicalSummary:
    """Build the full clinical summary. Never raises — degrades to an offline,
    rule-based summary when RAG/LLM are unavailable or fail."""
    findings = _abnormal_finding_strings(lab_analysis)
    meanings = _deterministic_meanings(lab_analysis)
    follow_ups = _deterministic_follow_ups(document_type, lab_analysis)

    chunks = []
    sources: list[str] = []
    confidence = 0.0
    if settings.DOCUMENT_USE_RAG:
        try:
            from backend.rag.retriever import get_retriever

            retriever = get_retriever()
            if retriever.available():
                query = _build_query(document_type, fields, lab_analysis)
                chunks = retriever.retrieve(query)
                sources = sorted({c.source for c in chunks})
                if chunks:
                    confidence = round(sum(c.score for c in chunks[:3]) / min(3, len(chunks)), 3)
        except Exception:  # noqa: BLE001 — RAG enrichment is best-effort
            logger.exception("RAG retrieval failed for document summary (continuing offline)")

    summary_text = _offline_summary(document_type, lab_analysis)
    explanation_text = (
        "; ".join(m.meaning for m in meanings) if meanings else
        "No abnormal findings were detected that require explanation."
    )
    provider = "offline"

    if settings.DOCUMENT_USE_LLM:
        try:
            from backend.llm import get_llm

            llm = get_llm()
            context = format_context(chunks)
            findings_block = "\n".join(f"- {f}" for f in findings) or "(no abnormal findings detected)"
            prompt = (
                f"Document type: {document_type.value.replace('_', ' ')}\n\n"
                f"Structured findings:\n{findings_block}\n\n"
                f"Retrieved medical knowledge context:\n{context}\n\n"
                "Using only the structured findings and context above, write the "
                "two labeled sections as instructed."
            )
            resp = await llm.acomplete(system=_SYSTEM_PROMPT, prompt=prompt, temperature=0.2, max_tokens=500)
            # Only trust the response over our deterministic text when either a
            # real cloud/local provider answered, or it followed the requested
            # two-section format — the offline extractive fallback just echoes
            # prompt text and matches neither condition.
            if resp.text.strip() and resp.provider != "offline":
                split_summary, split_explanation, matched = _split_llm_response(resp.text)
                summary_text = split_summary or summary_text
                if matched and split_explanation:
                    explanation_text = split_explanation
                provider = resp.provider
        except Exception:  # noqa: BLE001 — LLM generation is best-effort
            logger.exception("LLM summary generation failed for document (using offline summary)")

    return ClinicalSummary(
        summary=summary_text,
        abnormal_findings=findings,
        possible_meanings=meanings,
        follow_up_suggestions=follow_ups,
        ai_explanation=explanation_text,
        sources=sources,
        confidence=confidence,
        provider=provider,
        safety_note=SAFETY_FOOTER,
    )
