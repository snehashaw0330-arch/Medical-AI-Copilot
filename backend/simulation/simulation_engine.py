"""The scenario orchestrator for the Simulation Engine (async, best-effort).

Runs one "what-if" scenario end to end and builds the variant-vs-baseline
comparisons. For each scenario it:

1. applies the treatment edits (``treatment_engine``) and patient overrides
   (``patient_model``) to the baseline;
2. re-runs the existing subsystems on the *resulting* state — drug interactions
   (``drug_interactions``), disease prediction (``disease``) and knowledge-base
   evidence (reusing ``clinical_reasoning.evidence_engine``);
3. derives contraindications, side effects, treatment suggestions, clinical
   recommendations, disease + composite risk and a confidence breakdown
   (``recommendation_engine`` / ``risk_engine``).

Design contract (identical to the rest of the project): **async everywhere** (the
CPU-bound disease model runs in a worker thread via :func:`asyncio.to_thread`),
**best-effort** (any subsystem failure degrades that part only and is recorded in
``warnings`` — it never aborts the scenario), and **additive** (only reads from
the existing modules).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from backend.config import settings
from backend.simulation import (
    patient_model,
    recommendation_engine,
    risk_engine,
    treatment_engine,
)
from backend.simulation.schemas import (
    ComparisonDelta,
    DiseaseHypothesis,
    EvidenceCard,
    MedicineItem,
    PatientState,
    Scenario,
    ScenarioResult,
)

logger = logging.getLogger("simulation.engine")


class SimulationEngine:
    """Evaluates a single scenario and compares scenarios."""

    async def run_scenario(
        self,
        *,
        baseline_medicines: list[MedicineItem],
        base_patient: PatientState,
        scenario: Scenario,
        include_rag: bool,
        is_baseline: bool = False,
    ) -> ScenarioResult:
        warnings: list[str] = []

        # 1) Apply treatment + patient edits.
        resulting, applied = treatment_engine.apply_changes(
            baseline_medicines, scenario.medicine_changes
        )
        effective = patient_model.apply_patient_change(base_patient, scenario.patient_changes)
        flags = patient_model.derive_flags(effective)
        med_names = treatment_engine.names(resulting)

        # 2) Independent subsystem calls run concurrently.
        interactions_task = self._interactions(med_names, include_rag, warnings)
        disease_task = self._predict_disease(effective.symptoms, warnings)
        evidence_task = self._evidence(effective, med_names, warnings, include_rag)
        interactions, (hypotheses, resolved_syms), evidence = await asyncio.gather(
            interactions_task, disease_task, evidence_task,
        )
        resolved = (interactions or {}).get("resolved_medicines", []) or []
        unmatched = (interactions or {}).get("unmatched_medicines", []) or []

        # 3) Clinical synthesis (pure).
        contra = recommendation_engine.contraindications(resulting, flags)
        disease = risk_engine.disease_risk(hypotheses, flags)
        risk_level, risk_score = risk_engine.composite_risk(
            interactions=interactions, contraindications=contra, flags=flags, disease=disease,
        )
        side = recommendation_engine.side_effects(resulting)
        treatments = recommendation_engine.treatment_suggestions(resulting, flags, contra, interactions)
        recs = recommendation_engine.recommendations(contra, interactions, flags, risk_level)
        conf = recommendation_engine.confidence(
            medicines=resulting, resolved=resolved, unmatched=unmatched,
            interactions=interactions, evidence_count=len(evidence), flags=flags,
            has_symptoms=bool(effective.symptoms),
        )

        return ScenarioResult(
            scenario_id=scenario.id or uuid.uuid4().hex[:8],
            scenario_name=scenario.name,
            is_baseline=is_baseline,
            resulting_medicines=resulting,
            applied_changes=applied or (["No changes (baseline)."] if is_baseline else ["No changes applied."]),
            effective_patient=effective,
            drug_interactions=interactions,
            disease_risk=disease,
            clinical_recommendations=recs,
            treatment_suggestions=treatments,
            side_effects=side,
            contraindications=contra,
            evidence=evidence,
            confidence=conf,
            risk_level=risk_level,
            risk_score=risk_score,
            warnings=warnings,
        )

    # ==================================================================
    # Subsystem calls (best-effort)
    # ==================================================================
    async def _interactions(self, med_names, include_rag, warnings) -> dict | None:
        if len(med_names) < 2:
            return {"interactions": [], "resolved_medicines": med_names, "unmatched_medicines": []}
        try:
            from backend.drug_interactions import analyze_medicines

            report = await analyze_medicines(
                med_names, include_rag=include_rag and settings.SIMULATION_USE_RAG, persist=False,
            )
            return report.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Simulation interactions unavailable: %s", exc)
            warnings.append("Drug-interaction analysis was unavailable for this scenario.")
            return None

    async def _predict_disease(self, symptoms, warnings):
        if not (symptoms and settings.SIMULATION_PREDICT_DISEASE):
            return [], []
        try:
            from backend.disease.service import get_service as get_disease_service

            resp = await asyncio.to_thread(get_disease_service().predict, symptoms, 5)
            hyps = [
                DiseaseHypothesis(
                    disease=p.disease, confidence=p.confidence,
                    matched_symptoms=p.matched_symptoms, explanation=p.explanation,
                )
                for p in resp.predictions
            ]
            return hyps, [r.model_dump(mode="json") for r in resp.resolved_symptoms]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Simulation disease prediction unavailable: %s", exc)
            warnings.append("Disease prediction was unavailable for this scenario.")
            return [], []

    async def _evidence(self, patient, med_names, warnings, include_rag) -> list[EvidenceCard]:
        if not (include_rag and settings.SIMULATION_USE_RAG):
            return []
        try:
            from backend.clinical_reasoning.evidence_engine import get_engine as get_ev

            leading = patient.conditions[0] if patient.conditions else (
                patient.symptoms[0] if patient.symptoms else None
            )
            cards, _narrative, _conf = await get_ev().gather(
                disease=leading, diagnosis=None, symptoms=patient.symptoms,
                medicines=med_names, warnings=warnings,
            )
            return [
                EvidenceCard(id=c.id, title=c.title, source=c.source,
                             snippet=c.snippet, relevance=c.relevance)
                for c in cards
            ]
        except Exception as exc:  # noqa: BLE001
            logger.debug("Simulation evidence skipped: %s", exc)
            return []

    # ==================================================================
    # Comparison
    # ==================================================================
    def compare(self, base: ScenarioResult, variant: ScenarioResult) -> ComparisonDelta:
        """Compare a variant scenario against a reference (usually the baseline)."""
        base_pairs = _interaction_pairs(base)
        var_pairs = _interaction_pairs(variant)
        base_meds = {m.name.lower() for m in base.resulting_medicines}
        var_meds = {m.name.lower() for m in variant.resulting_medicines}
        base_contra = {c.medicine.lower() for c in base.contraindications}

        new_inter = sorted(var_pairs - base_pairs)
        resolved_inter = sorted(base_pairs - var_pairs)
        added = sorted({m.name for m in variant.resulting_medicines if m.name.lower() not in base_meds})
        removed = sorted({m.name for m in base.resulting_medicines if m.name.lower() not in var_meds})
        new_contra = sorted({c.medicine for c in variant.contraindications
                             if c.medicine.lower() not in base_contra})

        risk_delta = round(variant.risk_score - base.risk_score, 1)
        conf_delta = round(variant.confidence.overall - base.confidence.overall, 1)
        inter_delta = len(var_pairs) - len(base_pairs)
        safer = risk_delta < 0 and not new_contra

        return ComparisonDelta(
            from_scenario_id=base.scenario_id, from_scenario_name=base.scenario_name,
            to_scenario_id=variant.scenario_id, to_scenario_name=variant.scenario_name,
            risk_score_delta=risk_delta, confidence_delta=conf_delta,
            interaction_count_delta=inter_delta,
            new_interactions=new_inter, resolved_interactions=resolved_inter,
            added_medicines=added, removed_medicines=removed,
            new_contraindications=new_contra,
            verdict=_verdict(variant.scenario_name, base.scenario_name, risk_delta, new_contra, new_inter, resolved_inter),
            safer=safer,
        )


def _interaction_pairs(result: ScenarioResult) -> set[str]:
    pairs: set[str] = set()
    for it in (result.drug_interactions or {}).get("interactions", []) or []:
        members = it.get("pair") or it.get("medicines") or []
        if members:
            pairs.add(" + ".join(sorted(str(m).lower() for m in members)))
    return pairs


def _verdict(variant, base, risk_delta, new_contra, new_inter, resolved_inter) -> str:
    if new_contra:
        return f"{variant} introduces a contraindication ({', '.join(new_contra)}) — not recommended over {base}."
    if risk_delta < -1:
        extra = f" and clears {len(resolved_inter)} interaction(s)" if resolved_inter else ""
        return f"{variant} lowers composite risk by {abs(risk_delta):.0f} pts vs {base}{extra}."
    if risk_delta > 1:
        extra = f" and adds {len(new_inter)} interaction(s)" if new_inter else ""
        return f"{variant} raises composite risk by {risk_delta:.0f} pts vs {base}{extra}."
    return f"{variant} is broadly equivalent to {base} on composite risk."


_ENGINE: SimulationEngine | None = None


def get_engine() -> SimulationEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SimulationEngine()
    return _ENGINE
