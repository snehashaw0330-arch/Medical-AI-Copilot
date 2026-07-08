"""The step-by-step reasoning orchestrator (async, best-effort).

This is the heart of the Clinical Reasoning Platform. Instead of returning an
answer directly, it walks a fixed pipeline and records *every* stage as a
:class:`ReasoningStep` — with a status, a human summary and a structured detail
payload — so the UI can animate the flow and a clinician can audit each move:

    OCR ─► Medicine Detection ─► Medicine Validation ─► Drug Interactions ─►
    Disease Prediction ─► Retrieve Evidence (RAG) ─► Clinical Rules ─►
    Differential Diagnosis ─► Confidence ─► Final Recommendation

Design contract (identical to the other modules):

* **Async everywhere** — the disease model (CPU-bound, sync) runs in a worker
  thread via :func:`asyncio.to_thread`; interactions + RAG are awaited. The event
  loop is never blocked.
* **Best-effort** — every external call is wrapped so a failure marks *that step*
  ``failed`` and is recorded in ``warnings``; it never aborts the pipeline.
* **Additive** — it only *reads* from the existing subsystems (disease, drug
  interactions, RAG). No existing behaviour is changed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager

from backend.clinical_reasoning import (
    confidence_engine,
    evidence_engine,
    explanation_engine,
    medical_rules,
    recommendation_engine,
)
from backend.clinical_reasoning.medical_rules import ReasoningContext
from backend.clinical_reasoning.schemas import (
    ClinicalReasoningReport,
    ConfidenceAnalysisSection,
    DiagnosisStatus,
    DifferentialDiagnosis,
    DiseasePredictionSection,
    MedicineAnalysis,
    OCRFindings,
    PatientSummary,
    ReasoningRequest,
    ReasoningStep,
    StepStatus,
    utcnow,
)
from backend.config import settings

logger = logging.getLogger("clinical_reasoning.engine")


# Ordered pipeline definition: (key, display name).
_PIPELINE = [
    ("ocr", "OCR"),
    ("medicine_detection", "Medicine Detection"),
    ("medicine_validation", "Medicine Validation"),
    ("drug_interactions", "Drug Interaction Analysis"),
    ("disease_prediction", "Disease Prediction"),
    ("evidence_retrieval", "Retrieve Medical Evidence (RAG)"),
    ("clinical_rules", "Clinical Rules Evaluation"),
    ("differential", "Differential Diagnosis"),
    ("confidence", "Confidence Calculation"),
    ("recommendation", "Final Recommendation"),
]


class _StepRecorder:
    """Accumulates ReasoningStep objects with timing, keyed by pipeline order."""

    def __init__(self) -> None:
        self._steps: dict[str, ReasoningStep] = {
            key: ReasoningStep(order=i + 1, key=key, name=name)
            for i, (key, name) in enumerate(_PIPELINE)
        }

    @contextmanager
    def run(self, key: str):
        """Context manager that times a step and captures failures as ``failed``."""
        step = self._steps[key]
        step.status = StepStatus.RUNNING
        step.started_at = utcnow()
        t0 = time.perf_counter()
        try:
            yield step
            if step.status == StepStatus.RUNNING:
                step.status = StepStatus.COMPLETE
        except Exception as exc:  # noqa: BLE001 — one step never breaks the run
            step.status = StepStatus.FAILED
            step.title = "Step failed"
            step.summary = f"{step.name} could not complete: {exc}"
            logger.warning("Reasoning step '%s' failed: %s", key, exc)
        finally:
            step.finished_at = utcnow()
            step.duration_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    def skip(self, key: str, reason: str) -> None:
        step = self._steps[key]
        step.status = StepStatus.SKIPPED
        step.title = "Skipped"
        step.summary = reason

    def ordered(self) -> list[ReasoningStep]:
        return [self._steps[key] for key, _ in _PIPELINE]


class ReasoningEngine:
    """Runs the full reasoning pipeline and assembles the report."""

    async def run(self, req: ReasoningRequest) -> ClinicalReasoningReport:
        t_start = time.perf_counter()
        warnings: list[str] = []
        sources: list[str] = ["clinical-reasoning-engine"]
        rec = _StepRecorder()

        medicines = [m.strip() for m in req.medicines if m and m.strip()]
        symptoms = [s.strip() for s in req.symptoms if s and s.strip()]
        top_k = req.top_k or settings.CLINICAL_REASONING_TOP_K

        # ---- 1) OCR -----------------------------------------------------
        with rec.run("ocr") as step:
            detected = list(medicines)
            step.detail = {
                "raw_text_present": bool(req.ocr_text),
                "detected_medicines": detected,
                "diagnosis": req.diagnosis,
            }
            if req.ocr_text:
                step.title = f"OCR text supplied ({len(req.ocr_text)} chars)"
                step.summary = "Prescription text was provided upstream and carried into the reasoning."
            elif detected:
                step.title = f"{len(detected)} medicine(s) from upstream OCR"
                step.summary = "Medicines were supplied directly (no raw OCR text)."
            else:
                step.title = "No OCR input"
                step.summary = "No prescription text or medicines were supplied; reasoning proceeds from symptoms."
        ocr_findings = OCRFindings(
            raw_text=req.ocr_text, detected_medicines=list(medicines),
            diagnosis=req.diagnosis,
            note="OCR findings echoed from the upstream extraction.",
        )

        # ---- 2) Medicine Detection --------------------------------------
        with rec.run("medicine_detection") as step:
            step.detail = {"medicines": medicines}
            step.title = f"{len(medicines)} medicine(s) detected"
            step.summary = (", ".join(medicines) if medicines
                            else "No medicines to detect for this case.")
            if not medicines:
                step.status = StepStatus.SKIPPED

        # ---- 3 & 4) Validation + Interactions (reuse drug_interactions) --
        interaction_report: dict | None = None
        resolved: list[str] = []
        unmatched: list[str] = []
        if medicines:
            interaction_report, resolved, unmatched = await self._interactions(
                medicines, req, warnings,
            )
            with rec.run("medicine_validation") as step:
                step.detail = {"resolved": resolved, "unmatched": unmatched}
                step.title = f"{len(resolved)} resolved · {len(unmatched)} unresolved"
                step.summary = (
                    f"Matched {len(resolved)} medicine(s) to the database"
                    + (f"; could not resolve {', '.join(unmatched)}" if unmatched else ".")
                )
            with rec.run("drug_interactions") as step:
                inters = (interaction_report or {}).get("interactions") or []
                step.detail = {"interaction_count": len(inters), "report": interaction_report}
                step.title = (f"{len(inters)} interaction(s) found" if inters
                              else "No interactions found")
                step.summary = (
                    "Drug–drug interaction analysis ran on the resolved medicine list."
                    if interaction_report else "Interaction analysis was unavailable."
                )
            if interaction_report:
                sources.append("drug-interaction-dataset")
        else:
            rec.skip("medicine_validation", "No medicines supplied to validate.")
            rec.skip("drug_interactions", "Fewer than one medicine — no interactions to check.")

        # ---- 5) Disease Prediction --------------------------------------
        predictions, resolved_symptoms, disease_predicted = await self._predict_disease(
            req, symptoms, top_k, warnings,
        )
        with rec.run("disease_prediction") as step:
            step.detail = {
                "predictions": predictions,
                "resolved_symptoms": resolved_symptoms,
            }
            if predictions:
                top = predictions[0]
                step.title = f"Leading: {top['disease']} ({top['confidence']:.0f}%)"
                step.summary = f"{len(predictions)} candidate condition(s) ranked from the symptoms/inputs."
                sources.append("disease-prediction-model")
            elif not symptoms and not (req.disease or req.diagnosis):
                step.status = StepStatus.SKIPPED
                step.title = "No symptoms to predict from"
                step.summary = "No symptoms, disease or diagnosis were supplied."
            else:
                step.title = "No confident prediction"
                step.summary = "The inputs did not yield a recognised disease hypothesis."

        # ---- 6) Evidence retrieval (RAG) --------------------------------
        leading_name = predictions[0]["disease"] if predictions else (req.disease or req.diagnosis)
        evidence, rag_narrative, rag_conf = await evidence_engine.get_engine().gather(
            disease=leading_name, diagnosis=req.diagnosis,
            symptoms=symptoms, medicines=medicines, warnings=warnings,
        ) if req.include_rag else ([], None, 0.0)
        with rec.run("evidence_retrieval") as step:
            step.detail = {"evidence_count": len(evidence), "narrative": rag_narrative}
            if not req.include_rag:
                step.status = StepStatus.SKIPPED
                step.title = "Evidence retrieval disabled"
                step.summary = "RAG enrichment was turned off for this request."
            elif evidence:
                step.title = f"{len(evidence)} evidence document(s) retrieved"
                step.summary = "Relevant passages were retrieved from the knowledge base to ground the reasoning."
                sources.append("rag-knowledge-base")
            else:
                step.title = "No evidence retrieved"
                step.summary = "The knowledge base returned no grounding passages for this case."

        # ---- 7) Clinical Rules ------------------------------------------
        ctx = ReasoningContext(
            age=req.age, gender=req.gender, symptoms=symptoms,
            disease=leading_name, diagnosis=req.diagnosis,
            medicines=medicines, resolved_medicines=resolved,
            unmatched_medicines=unmatched, interaction_report=interaction_report or {},
        )
        rules = medical_rules.evaluate(ctx)
        with rec.run("clinical_rules") as step:
            step.detail = {"rules": [r.model_dump(mode="json") for r in rules]}
            step.title = f"{len(rules)} rule(s) fired" if rules else "No rules fired"
            step.summary = ("; ".join(r.name for r in rules[:4]) if rules
                            else "No deterministic clinical rules matched this case.")
            if rules:
                sources.append("clinical-rules-engine")

        # ---- 8) Differential Diagnosis ----------------------------------
        expl_engine = explanation_engine.get_engine()
        differential = expl_engine.build_differential(predictions, symptoms)
        with rec.run("differential") as step:
            step.detail = {"differential": [d.model_dump(mode="json") for d in differential]}
            considered = [d for d in differential if d.status != DiagnosisStatus.REJECTED]
            rejected = [d for d in differential if d.status == DiagnosisStatus.REJECTED]
            if differential:
                step.title = f"{len(considered)} kept · {len(rejected)} rejected"
                step.summary = "Ranked the candidates and recorded why the weaker ones were ruled out."
            else:
                step.status = StepStatus.SKIPPED
                step.title = "No differential"
                step.summary = "No candidate conditions to differentiate."

        leading = next((d for d in differential if d.status == DiagnosisStatus.LEADING), None)

        # ---- 9) Confidence ----------------------------------------------
        conf = confidence_engine.get_engine().compute(
            hypotheses=differential, rules=rules,
            evidence_confidence=rag_conf, evidence_count=len(evidence),
            has_symptoms=bool(symptoms), has_medicines=bool(medicines),
            has_age=req.age is not None, has_gender=bool(req.gender),
            has_disease_or_dx=bool(req.disease or req.diagnosis),
            disease_predicted=disease_predicted,
        )
        with rec.run("confidence") as step:
            step.detail = {"breakdown": conf.model_dump(mode="json")}
            step.title = f"{conf.overall:.0f}% — {conf.level.value.replace('_', ' ')}"
            step.summary = conf.rationale

        # ---- 10) Recommendation -----------------------------------------
        rec_engine = recommendation_engine.get_engine()
        risk = recommendation_engine.overall_risk(rules, interaction_report)
        recommendations = rec_engine.build_recommendations(
            leading=leading, rules=rules, interaction_report=interaction_report,
            confidence=conf, risk=risk,
        )
        follow_up = rec_engine.build_follow_up(risk=risk, leading=leading, rules=rules)
        references = rec_engine.build_references(
            evidence=evidence, rules=rules,
            used_model=disease_predicted, used_interactions=bool(interaction_report),
        )
        with rec.run("recommendation") as step:
            step.detail = {
                "recommendations": [r.model_dump(mode="json") for r in recommendations],
                "risk_level": risk.value,
            }
            step.title = f"{len(recommendations)} recommendation(s) · risk {risk.value}"
            step.summary = "Synthesised graded, individually-justified clinical recommendations."

        # ---- Assemble the explanation + report --------------------------
        explanation = expl_engine.build_explanation(
            differential=differential, reported_symptoms=symptoms,
            resolved_symptoms=resolved_symptoms, medicines=medicines,
            resolved=resolved, unmatched=unmatched,
            interaction_report=interaction_report, evidence=evidence,
            rules=rules, confidence=conf,
            leading_raw_explanation=(predictions[0].get("explanation", "") if predictions else ""),
        )

        report = ClinicalReasoningReport(
            created_at=utcnow(),
            duration_ms=round((time.perf_counter() - t_start) * 1000.0, 1),
            patient_summary=PatientSummary(
                age=req.age, gender=req.gender,
                symptom_count=len(symptoms), medicine_count=len(medicines),
                narrative=self._patient_narrative(req, symptoms, medicines, leading),
            ),
            ocr_findings=ocr_findings,
            medicine_analysis=MedicineAnalysis(
                insights=explanation.influencing_medicines,
                resolved=resolved, unresolved=unmatched,
                note=(rag_narrative or "").strip()[:400] or "",
            ),
            disease_prediction=DiseasePredictionSection(
                leading=leading,
                hypotheses=differential,
                method=("Symptom-driven ML prediction" if disease_predicted
                        else "Caller-supplied diagnosis" if (req.disease or req.diagnosis)
                        else "No diagnosis derived"),
            ),
            clinical_evidence=evidence,
            reasoning_chain=rec.ordered(),
            drug_interaction_analysis=interaction_report,
            confidence_analysis=ConfidenceAnalysisSection(breakdown=conf),
            alternative_diagnoses=[
                d for d in differential if d.status != DiagnosisStatus.LEADING
            ],
            clinical_recommendations=recommendations,
            follow_up_suggestions=follow_up,
            medical_references=references,
            explanation=explanation,
            matched_rules=rules,
            risk_level=risk,
            confidence=conf.overall,
            warnings=warnings,
            sources=sorted(set(sources)),
        )
        logger.info(
            "Reasoning complete: leading=%s risk=%s conf=%.1f steps=%d (%.0f ms)",
            leading.disease if leading else "none", risk.value, conf.overall,
            len(report.reasoning_chain), report.duration_ms,
        )
        return report

    # -- subsystem calls (best-effort) ------------------------------------
    async def _interactions(
        self, medicines: list[str], req: ReasoningRequest, warnings: list[str],
    ) -> tuple[dict | None, list[str], list[str]]:
        """Run drug-interaction analysis; return (report, resolved, unmatched)."""
        try:
            from backend.drug_interactions import analyze_medicines

            report = await analyze_medicines(
                medicines,
                include_rag=req.include_rag and settings.CLINICAL_REASONING_USE_RAG,
                persist=False,
                source_record_id=req.source_record_id,
            )
            data = report.model_dump(mode="json")
            return (
                data,
                data.get("resolved_medicines", []) or [],
                data.get("unmatched_medicines", []) or [],
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("Interaction analysis unavailable: %s", exc)
            warnings.append("Drug-interaction analysis was unavailable for this case.")
            return None, [], list(medicines)

    async def _predict_disease(
        self, req: ReasoningRequest, symptoms: list[str], top_k: int,
        warnings: list[str],
    ) -> tuple[list[dict], list[dict], bool]:
        """Return (predictions, resolved_symptoms, disease_predicted)."""
        # Caller-supplied disease/diagnosis is trusted as the working diagnosis.
        seed: list[dict] = []
        if req.disease:
            seed.append({"disease": req.disease, "confidence": 90.0,
                         "matched_symptoms": symptoms,
                         "explanation": "Condition supplied by the caller.",
                         "source": "input"})
        elif req.diagnosis:
            seed.append({"disease": req.diagnosis, "confidence": 85.0,
                         "matched_symptoms": symptoms,
                         "explanation": "Diagnosis parsed from the prescription.",
                         "source": "diagnosis"})

        should_predict = (
            req.run_disease_prediction
            and settings.CLINICAL_REASONING_PREDICT_DISEASE
            and symptoms
            and not seed
        )
        if not should_predict:
            return seed, [], False

        try:
            from backend.disease.service import get_service as get_disease_service

            svc = get_disease_service()
            resp = await asyncio.to_thread(svc.predict, symptoms, top_k)
            preds = [
                {"disease": p.disease, "confidence": p.confidence,
                 "matched_symptoms": p.matched_symptoms,
                 "explanation": p.explanation, "source": "model"}
                for p in resp.predictions
            ]
            resolved_symptoms = [r.model_dump(mode="json") for r in resp.resolved_symptoms]
            if not preds:
                warnings.append("The symptoms provided were not recognised by the disease model.")
            return preds, resolved_symptoms, bool(preds)
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("Disease prediction unavailable: %s", exc)
            warnings.append("Disease prediction was unavailable for this case.")
            return seed, [], False

    def _patient_narrative(
        self, req: ReasoningRequest, symptoms: list[str], medicines: list[str],
        leading: DifferentialDiagnosis | None,
    ) -> str:
        bits: list[str] = []
        who = []
        if req.age is not None:
            who.append(f"{req.age}-year-old")
        if req.gender:
            who.append(req.gender.lower())
        bits.append((" ".join(who) + " patient").strip().capitalize() if who else "Patient")
        if symptoms:
            bits.append(f"presenting with {', '.join(symptoms[:6])}")
        if medicines:
            bits.append(f"on {', '.join(medicines[:6])}")
        sentence = " ".join(bits).strip() + "."
        if leading is not None:
            sentence += f" Working diagnosis: {leading.disease} ({leading.confidence:.0f}%)."
        return sentence


_ENGINE: ReasoningEngine | None = None


def get_engine() -> ReasoningEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ReasoningEngine()
    return _ENGINE
