"""Recommendation composition for the Clinical Decision Support module.

Pure functions (no I/O) that turn the raw rules-engine findings + the computed
risk level + the disease hypotheses into the polished, prioritised lists the UI
shows: recommended next steps, follow-up advice, and a human-readable clinical
summary.

Keeping this separate from :mod:`rules_engine` (which owns *medical knowledge*)
means the *presentation and prioritisation* logic — risk-tier escalation
messages, ordering, phrasing — lives in one auditable place.
"""

from __future__ import annotations

from backend.clinical_decision.rules_engine import ClinicalContext, RuleFindings
from backend.clinical_decision.schemas import DiseaseHypothesis, RiskLevel

# Generic next-step guidance added per risk tier (most urgent first).
_RISK_NEXT_STEPS: dict[RiskLevel, list[str]] = {
    RiskLevel.CRITICAL: [
        "Escalate now: arrange emergency / urgent-care review before continuing.",
        "Do not delay treatment of any red-flag finding pending investigations.",
    ],
    RiskLevel.HIGH: [
        "Arrange prompt clinician review of the flagged findings.",
        "Re-check the medication list and interaction report before dispensing.",
    ],
    RiskLevel.MODERATE: [
        "Have a clinician confirm the plan and address the noted cautions.",
        "Counsel the patient on the relevant warnings before starting therapy.",
    ],
    RiskLevel.LOW: [
        "Proceed with routine care; confirm the medication list with the patient.",
    ],
}

_RISK_FOLLOWUP: dict[RiskLevel, str] = {
    RiskLevel.CRITICAL: "Immediate reassessment — do not wait for a routine appointment.",
    RiskLevel.HIGH: "Follow up within 24–48 hours or sooner if symptoms worsen.",
    RiskLevel.MODERATE: "Follow up within a few days to confirm response and tolerance.",
    RiskLevel.LOW: "Routine follow-up; return sooner if new or worsening symptoms appear.",
}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def build_next_steps(
    findings: RuleFindings,
    risk_level: RiskLevel,
) -> list[str]:
    """Compose the prioritised 'recommended next steps' list.

    Risk-tier guidance comes first (it's the most actionable), followed by any
    specific next steps the rules produced, then a work-up prompt if labs were
    recommended.
    """
    steps: list[str] = list(_RISK_NEXT_STEPS.get(risk_level, []))
    steps.extend(findings.recommended_next_steps)
    if findings.recommended_lab_tests:
        steps.append("Order the recommended baseline / monitoring investigations.")
    if findings.missing_information:
        steps.append("Gather the missing information listed below to sharpen the assessment.")
    return _dedupe(steps)


def build_follow_up(
    findings: RuleFindings,
    risk_level: RiskLevel,
) -> list[str]:
    """Compose the follow-up advice list (risk-tier default + rule-specific)."""
    out: list[str] = [_RISK_FOLLOWUP.get(risk_level, _RISK_FOLLOWUP[RiskLevel.LOW])]
    out.extend(findings.follow_up)
    return _dedupe(out)


def _describe_patient(ctx: ClinicalContext) -> str:
    bits: list[str] = []
    if ctx.age is not None:
        bits.append(f"{ctx.age}-year-old")
    if ctx.gender:
        bits.append(ctx.gender.lower())
    who = " ".join(bits) if bits else "Patient"
    return who[0].upper() + who[1:]


def build_summary(
    ctx: ClinicalContext,
    findings: RuleFindings,
    diseases: list[DiseaseHypothesis],
    risk_level: RiskLevel,
    interaction_report: dict | None,
) -> str:
    """Compose a concise, human-readable clinical summary paragraph."""
    sentences: list[str] = []

    # 1) Who + presenting picture.
    who = _describe_patient(ctx)
    if ctx.symptoms:
        sym = ", ".join(ctx.symptoms[:6])
        sentences.append(f"{who} presenting with {sym}.")
    else:
        sentences.append(f"{who}; no presenting symptoms were provided.")

    # 2) Medications.
    n_meds = len(ctx.resolved_medicines or ctx.medicines)
    if n_meds:
        names = ", ".join((ctx.resolved_medicines or ctx.medicines)[:8])
        sentences.append(
            f"{n_meds} medication(s) identified: {names}."
            + (f" {len(ctx.unmatched_medicines)} could not be matched."
               if ctx.unmatched_medicines else "")
        )
    else:
        sentences.append("No medications were provided for review.")

    # 3) Leading hypothesis.
    if diseases:
        top = diseases[0]
        conf = f" ({top.confidence:.0f}% model confidence)" if top.source == "model" else ""
        sentences.append(f"Most likely condition: {top.disease}{conf}.")

    # 4) Interaction headline.
    inter = interaction_report or {}
    n_inter = len(inter.get("interactions", []) or [])
    if n_inter:
        sentences.append(
            f"{n_inter} potential drug interaction(s) found; highest severity "
            f"{(inter.get('overall_risk') or 'none').upper()}."
        )

    # 5) Risk headline.
    n_flags = len(findings.red_flags)
    flag_txt = f" with {n_flags} red-flag alert(s)" if n_flags else ""
    sentences.append(
        f"Overall clinical risk assessed as {risk_level.value.upper()}{flag_txt}. "
        "Clinician verification required."
    )

    return " ".join(sentences)


def compute_confidence(
    ctx: ClinicalContext,
    diseases: list[DiseaseHypothesis],
    interaction_report: dict | None,
    rag_confidence: float,
) -> float:
    """Estimate how complete and well-grounded this report is (0..100).

    A blend of input completeness, how many medicines resolved to the knowledge
    base, the disease model's own confidence, and RAG retrieval confidence. This
    is a *confidence in the analysis*, not a diagnostic certainty.
    """
    present = [
        ctx.age is not None,
        bool((ctx.gender or "").strip()),
        bool(ctx.symptoms),
        bool(ctx.disease or ctx.diagnosis),
        bool(ctx.medicines),
    ]
    completeness = sum(present) / len(present)

    meds = ctx.medicines
    resolution = (
        len(ctx.resolved_medicines) / len(meds) if meds else 1.0
    )

    disease_conf = (diseases[0].confidence / 100.0) if diseases else 0.5
    rag_conf = max(0.0, min(rag_confidence, 1.0))

    score = (
        0.35 * completeness
        + 0.25 * resolution
        + 0.20 * disease_conf
        + 0.20 * rag_conf
    )
    return round(score * 100, 1)
