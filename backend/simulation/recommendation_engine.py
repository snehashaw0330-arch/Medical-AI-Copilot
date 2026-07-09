"""Clinical synthesis for the Simulation Engine (pure, deterministic).

Given the resulting medicines + the effective patient (and the interaction
sub-report), this engine derives the four clinical deliverables the product
requires for every simulation — **contraindications**, **side effects**,
**treatment suggestions** and **clinical recommendations** — plus a weighted,
auditable **confidence breakdown**.

The clinical knowledge here is a transparent, curated safety net (teratogens,
renally-cleared / nephrotoxic drugs, hepatotoxic drugs, common side effects,
penicillin cross-reactivity). It layers on top of the live drug-interaction
dataset and the RAG evidence the simulation also gathers — it is never the sole
basis for a recommendation, and everything is grounded in the specific inputs.
"""

from __future__ import annotations

from backend.simulation.patient_model import PatientFlags
from backend.simulation.schemas import (
    ConfidenceBreakdown,
    ConfidenceComponent,
    Contraindication,
    MedicineItem,
    Recommendation,
    RiskLevel,
    SideEffect,
    TreatmentSuggestion,
)

# --------------------------------------------------------------------------
# Curated knowledge (substring match on the lowercased medicine name)
# --------------------------------------------------------------------------
_TERATOGENS = {
    "warfarin", "isotretinoin", "methotrexate", "valproate", "valproic",
    "lisinopril", "enalapril", "ramipril", "losartan", "candesartan",
    "ibuprofen", "naproxen", "diclofenac", "atorvastatin", "simvastatin",
}
_NEPHROTOXIC = {"ibuprofen", "naproxen", "diclofenac", "gentamicin", "metformin", "lithium"}
_HEPATOTOXIC = {"paracetamol", "acetaminophen", "isoniazid", "methotrexate", "statin",
                "atorvastatin", "simvastatin", "amiodarone"}
_SIDE_EFFECTS: dict[str, list[tuple[str, str]]] = {
    "paracetamol": [("Hepatotoxicity in overdose", "rare"), ("Nausea", "possible")],
    "acetaminophen": [("Hepatotoxicity in overdose", "rare")],
    "amoxicillin": [("Diarrhoea", "common"), ("Rash", "possible")],
    "ibuprofen": [("GI irritation / bleeding", "common"), ("Renal impairment", "possible")],
    "naproxen": [("GI irritation / bleeding", "common")],
    "warfarin": [("Bleeding", "common"), ("Bruising", "common")],
    "aspirin": [("GI bleeding", "possible"), ("Tinnitus at high dose", "rare")],
    "metformin": [("GI upset", "common"), ("Lactic acidosis", "rare")],
    "atorvastatin": [("Myalgia", "possible"), ("Deranged LFTs", "possible")],
    "amlodipine": [("Ankle oedema", "common"), ("Flushing", "possible")],
    "omeprazole": [("Headache", "possible"), ("Hypomagnesaemia", "rare")],
}
# Allergy cross-reactivity families.
_CROSS_REACT = {
    "penicillin": {"amoxicillin", "ampicillin", "flucloxacillin", "co-amoxiclav", "penicillin"},
    "sulfa": {"sulfamethoxazole", "co-trimoxazole", "sulfasalazine"},
    "nsaid": {"ibuprofen", "naproxen", "diclofenac", "aspirin"},
}


def _hit(name: str, needles: set[str]) -> bool:
    n = name.lower()
    return any(k in n for k in needles)


# --------------------------------------------------------------------------
# Contraindications
# --------------------------------------------------------------------------
def contraindications(
    medicines: list[MedicineItem], flags: PatientFlags
) -> list[Contraindication]:
    out: list[Contraindication] = []
    for m in medicines:
        name = m.name
        low = name.lower()

        # Allergy (direct or cross-reactivity) — the most serious.
        for allergen in flags.allergies:
            family = _CROSS_REACT.get(allergen, {allergen})
            if allergen in low or _hit(low, family):
                out.append(Contraindication(
                    medicine=name,
                    reason=f"Patient reports allergy to '{allergen}'"
                           + ("" if allergen in low else " (cross-reactivity)"),
                    severity=RiskLevel.CRITICAL, factor="allergy",
                ))
                break

        if flags.is_pregnant and _hit(low, _TERATOGENS):
            out.append(Contraindication(
                medicine=name, reason="Known/possible teratogen — avoid in pregnancy.",
                severity=RiskLevel.HIGH, factor="pregnancy",
            ))
        if flags.renal_severe and _hit(low, _NEPHROTOXIC):
            out.append(Contraindication(
                medicine=name, reason="Nephrotoxic / renally-cleared — avoid in severe renal impairment.",
                severity=RiskLevel.HIGH, factor="renal",
            ))
        if flags.hepatic_severe and _hit(low, _HEPATOTOXIC):
            out.append(Contraindication(
                medicine=name, reason="Hepatotoxic — avoid / reduce in severe hepatic impairment.",
                severity=RiskLevel.HIGH, factor="hepatic",
            ))
    return out


# --------------------------------------------------------------------------
# Side effects
# --------------------------------------------------------------------------
def side_effects(medicines: list[MedicineItem]) -> list[SideEffect]:
    out: list[SideEffect] = []
    for m in medicines:
        low = m.name.lower()
        for key, effects in _SIDE_EFFECTS.items():
            if key in low:
                for effect, likelihood in effects:
                    out.append(SideEffect(medicine=m.name, effect=effect, likelihood=likelihood))
                break
    return out


# --------------------------------------------------------------------------
# Treatment suggestions
# --------------------------------------------------------------------------
def treatment_suggestions(
    medicines: list[MedicineItem], flags: PatientFlags,
    contra: list[Contraindication], interactions: dict | None,
) -> list[TreatmentSuggestion]:
    out: list[TreatmentSuggestion] = []

    for c in contra:
        out.append(TreatmentSuggestion(
            suggestion=f"Reconsider {c.medicine}",
            rationale=c.reason,
            caution="Choose an agent appropriate for this patient's status.",
        ))

    if flags.renal_impaired:
        out.append(TreatmentSuggestion(
            suggestion="Apply renal dose adjustment",
            rationale="Renal impairment reduces clearance of renally-eliminated drugs.",
            caution="Check eGFR-based dosing for each renally-cleared medicine.",
        ))
    if flags.hepatic_impaired:
        out.append(TreatmentSuggestion(
            suggestion="Monitor liver function and avoid hepatotoxic agents",
            rationale="Hepatic impairment alters metabolism of many drugs.",
        ))
    if flags.is_paediatric or flags.low_body_weight:
        out.append(TreatmentSuggestion(
            suggestion="Use weight-based dosing",
            rationale="Paediatric / low body weight makes fixed adult doses unsafe.",
        ))
    if flags.is_pregnant:
        out.append(TreatmentSuggestion(
            suggestion="Prefer pregnancy-safe alternatives",
            rationale="Several agents in the list carry pregnancy-safety concerns.",
        ))
    if interactions and (interactions.get("interactions") or []):
        out.append(TreatmentSuggestion(
            suggestion="Reconcile the flagged drug interactions",
            rationale=f"{len(interactions['interactions'])} interaction(s) detected in the new list.",
            caution="Adjust, space or substitute the interacting medicines.",
        ))
    if not out:
        out.append(TreatmentSuggestion(
            suggestion="No specific adjustment indicated by the simulation",
            rationale="No contraindications, patient risk factors or interactions were detected.",
        ))
    out.append(TreatmentSuggestion(
        suggestion="Confirm with a qualified clinician before any change",
        rationale="This is an educational simulation, not a medical order.",
    ))
    return out


# --------------------------------------------------------------------------
# Clinical recommendations
# --------------------------------------------------------------------------
def recommendations(
    contra: list[Contraindication], interactions: dict | None,
    flags: PatientFlags, risk_level: RiskLevel,
) -> list[Recommendation]:
    out: list[Recommendation] = []
    for c in contra:
        if c.severity in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            out.append(Recommendation(
                title=f"Avoid / review {c.medicine}",
                detail=c.reason, priority=c.severity,
                rationale=f"Contraindication driven by {c.factor}.",
            ))
    if interactions and (interactions.get("interactions") or []):
        out.append(Recommendation(
            title="Manage the projected drug interactions",
            detail="The simulated medicine list introduces interaction risk.",
            priority=RiskLevel.HIGH if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else RiskLevel.MODERATE,
            rationale="From the drug-interaction analysis of the resulting list.",
        ))
    if not out:
        out.append(Recommendation(
            title="No blocking safety issue detected in this scenario",
            detail="The simulated change did not surface a contraindication or new interaction.",
            priority=RiskLevel.LOW, rationale="Composite risk stayed within acceptable bounds.",
        ))
    out.append(Recommendation(
        title="Clinician verification required",
        detail="Confirm the simulated plan against full clinical context before acting.",
        priority=RiskLevel.LOW, rationale="Simulation is a decision-support aid only.",
    ))
    return out


# --------------------------------------------------------------------------
# Confidence
# --------------------------------------------------------------------------
_WEIGHTS = {
    "input_completeness": 0.30,
    "medicine_resolution": 0.25,
    "interaction_data": 0.20,
    "evidence_grounding": 0.25,
}


def confidence(
    *, medicines: list[MedicineItem], resolved: list[str], unmatched: list[str],
    interactions: dict | None, evidence_count: int, flags: PatientFlags,
    has_symptoms: bool,
) -> ConfidenceBreakdown:
    components: list[ConfidenceComponent] = []
    missing: list[str] = []

    # Input completeness — patient factors + symptoms known.
    known = sum([
        flags.allergies != () or True,  # allergies field always considered
        has_symptoms,
        len(medicines) > 0,
    ])
    ic = min(100.0, 40.0 + known * 20.0)
    if not has_symptoms:
        missing.append("presenting symptoms")
    components.append(_c("input_completeness", ic,
                         "All key inputs present." if has_symptoms else "No symptoms supplied."))

    # Medicine resolution — how many names matched the dataset.
    total = max(1, len(medicines))
    mr = 100.0 * (len(resolved) / total) if resolved else (50.0 if medicines else 0.0)
    if unmatched:
        missing.append(f"{len(unmatched)} unresolved medicine name(s)")
    components.append(_c("medicine_resolution", mr,
                         f"{len(resolved)}/{total} medicine(s) matched the dataset."))

    # Interaction data availability.
    idata = 90.0 if interactions is not None else 20.0
    components.append(_c("interaction_data", idata,
                         "Interaction analysis ran." if interactions is not None else "Interaction analysis unavailable."))

    # Evidence grounding.
    eg = min(100.0, evidence_count * 25.0)
    if evidence_count == 0:
        missing.append("supporting knowledge-base evidence")
    components.append(_c("evidence_grounding", eg,
                         f"{evidence_count} evidence document(s)." if evidence_count else "No evidence retrieved."))

    overall = round(sum(c.contribution for c in components), 1)
    overall = max(0.0, min(100.0, overall))
    level = ("very_high" if overall >= 85 else "high" if overall >= 68
             else "moderate" if overall >= 45 else "low" if overall >= 25 else "very_low")
    strongest = max(components, key=lambda c: c.contribution)
    rationale = (
        f"Overall confidence is {level.replace('_', ' ')}. Strongest support: "
        f"{strongest.name.replace('_', ' ')} ({strongest.score:.0f}/100)."
        + (f" Would improve with: {', '.join(missing)}." if missing else "")
    )
    return ConfidenceBreakdown(
        overall=overall, level=level, components=components,
        missing_information=missing, rationale=rationale,
    )


def _c(key: str, score: float, note: str) -> ConfidenceComponent:
    score = round(max(0.0, min(100.0, score)), 1)
    w = _WEIGHTS[key]
    return ConfidenceComponent(
        name=key, weight=w, score=score, contribution=round(w * score, 1), note=note,
    )
