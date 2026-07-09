"""The 11-stage Copilot workflow orchestrator (async, best-effort).

This is where the Copilot "does the work". It chains every existing module in a
fixed order and records each stage in a :class:`~backend.copilot.reasoning.WorkflowTrace`:

    1  Receive prescription            7  Generate Clinical Decision
    2  Run OCR                         8  Generate AI Summary
    3  Extract medicines               9  Generate Treatment Suggestions
    4  Check drug interactions        10  Generate Follow-up Suggestions
    5  Predict disease                11  Generate Final Medical Report
    6  Retrieve medical evidence

Design contract (identical to the rest of the project):

* **Async everywhere** — the CPU-bound OCR pipeline runs in a worker thread via
  :func:`asyncio.to_thread`; every other module call is awaited.
* **Best-effort** — each stage is wrapped so a failure marks *that stage* failed
  (in the trace + activity timeline) and the workflow continues. It never raises.
* **Additive** — it only *reads* from OCR, disease, drug-interactions, RAG,
  clinical-decision and the report generator; it changes none of them.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from backend.config import settings
from backend.copilot import planner
from backend.copilot.reasoning import WorkflowTrace
from backend.copilot.schemas import (
    CopilotAnalysis,
    DiseaseHypothesis,
    EvidenceCard,
    MedicalReference,
    OCRSummary,
    Recommendation,
    StepStatus,
    utcnow,
)
from backend.copilot.summary import get_engine as get_summary_engine

logger = logging.getLogger("copilot.workflow")


def _parse_medicines_from_text(text: str) -> list[str]:
    """Very small helper to pull candidate medicine tokens from free text."""
    if not text:
        return []
    out: list[str] = []
    for chunk in text.replace("\n", ",").split(","):
        name = chunk.strip()
        # Keep short-ish alphabetic-leading tokens; skip obvious non-medicine lines.
        if 2 <= len(name) <= 40 and name[0].isalpha():
            out.append(name)
    return out[:20]


class CopilotWorkflow:
    """Runs the full 11-stage pipeline and assembles a :class:`CopilotAnalysis`."""

    async def run(
        self,
        *,
        session_id: str,
        image_path: str | None,
        text: str,
        medicines: list[str],
        symptoms: list[str],
        patient_name: str | None,
        age: int | None,
        gender: str | None,
        diagnosis: str | None,
        include_rag: bool,
    ) -> CopilotAnalysis:
        t0 = time.perf_counter()
        trace = WorkflowTrace()
        warnings: list[str] = []
        sources: list[str] = ["copilot"]

        pl = planner.plan(planner.WorkflowInputs(
            has_file=bool(image_path), text=text, medicines=medicines,
            symptoms=symptoms, diagnosis=diagnosis, include_rag=include_rag,
        ))

        # ---- 1) Receive -------------------------------------------------
        with trace.step("receive") as s:
            s.title = "Inputs received"
            s.summary = (
                f"{'Prescription image' if image_path else 'Manual inputs'} received"
                f" · {len(medicines)} medicine(s), {len(symptoms)} symptom(s)."
            )
            s.detail = {"has_file": bool(image_path), "symptoms": symptoms}
        trace.activity_event("Inputs received", step_key="receive")

        # ---- 2) OCR -----------------------------------------------------
        ocr_summary: OCRSummary | None = None
        ocr_result_dict: dict | None = None
        ocr_medicines: list[str] = []
        if pl.should("ocr"):
            ocr_summary, ocr_result_dict, ocr_medicines = await self._run_ocr(
                image_path, trace, warnings,
            )
            if ocr_result_dict:
                sources.append("ocr")
                # Backfill patient fields from OCR when the caller didn't supply them.
                f = ocr_result_dict.get("fields") or {}
                patient_name = patient_name or f.get("patient")
                gender = gender or (f.get("gender") or None)
                diagnosis = diagnosis or f.get("diagnosis")
        else:
            trace.skip("ocr", pl.reason("ocr"))

        # ---- 3) Extract medicines --------------------------------------
        all_medicines: list[str] = []
        with trace.step("extract_medicines") as s:
            merged = _dedupe(ocr_medicines + medicines + _parse_medicines_from_text(text))
            all_medicines = merged
            s.title = f"{len(all_medicines)} medicine(s) extracted"
            s.summary = ", ".join(all_medicines) if all_medicines else "No medicines identified."
            s.detail = {"medicines": all_medicines}
            if not all_medicines:
                s.status = StepStatus.SKIPPED
        if all_medicines:
            trace.activity_event(
                "Medicines Found", detail=", ".join(all_medicines[:8]), step_key="extract_medicines",
            )

        # ---- 4) Drug interactions --------------------------------------
        interactions: dict | None = None
        resolved: list[str] = []
        if pl.should("drug_interactions") and len(all_medicines) >= 2:
            interactions, resolved = await self._interactions(all_medicines, include_rag, trace, warnings)
            if interactions:
                sources.append("drug-interaction-dataset")
                trace.activity_event(
                    "Drug Interaction Completed",
                    detail=f"{len(interactions.get('interactions') or [])} interaction(s)",
                    step_key="drug_interactions",
                )
        else:
            trace.skip("drug_interactions",
                       pl.reason("drug_interactions") or "Fewer than two medicines to compare.")

        # ---- 5) Disease prediction -------------------------------------
        diseases: list[DiseaseHypothesis] = []
        if pl.should("disease_prediction"):
            diseases = await self._predict_disease(symptoms, diagnosis, trace, warnings)
            if diseases:
                sources.append("disease-prediction-model")
                trace.activity_event(
                    "Disease Prediction Completed",
                    detail=f"{diseases[0].disease} ({diseases[0].confidence:.0f}%)",
                    step_key="disease_prediction",
                )
        else:
            trace.skip("disease_prediction", pl.reason("disease_prediction"))

        # ---- 6) Evidence retrieval (RAG) -------------------------------
        evidence: list[EvidenceCard] = []
        if pl.should("evidence"):
            evidence = await self._evidence(
                diseases, diagnosis, symptoms, all_medicines, trace, warnings,
            )
            if evidence:
                sources.append("rag-knowledge-base")
                trace.activity_event(
                    "Medical Evidence Retrieved", detail=f"{len(evidence)} document(s)", step_key="evidence",
                )
        else:
            trace.skip("evidence", pl.reason("evidence"))

        # ---- 7) Clinical decision --------------------------------------
        clinical: dict | None = None
        if pl.should("clinical_decision"):
            clinical = await self._clinical_decision(
                all_medicines, symptoms, diagnosis, diseases, age, gender,
                interactions, include_rag, trace, warnings,
            )
            if clinical:
                sources.append("clinical-decision-support")
                trace.activity_event(
                    "Clinical Recommendation Generated",
                    detail=f"risk: {clinical.get('risk_level', 'low')}", step_key="clinical_decision",
                )
        else:
            trace.skip("clinical_decision", pl.reason("clinical_decision"))

        # Roll up confidence + risk from the richest available source.
        risk_level = (clinical or {}).get("risk_level", "low")
        confidence = self._confidence(clinical, diseases)

        # ---- 8) AI summary ---------------------------------------------
        summary_engine = get_summary_engine()
        patient_line = self._patient_line(patient_name, age, gender, symptoms)
        summary_text = ""
        with trace.step("summary") as s:
            summary_text, provider = await summary_engine.summary(
                medicines=all_medicines, interactions=interactions, diseases=diseases,
                evidence_titles=[e.title for e in evidence], patient=patient_line,
            )
            s.title = f"AI summary generated ({provider})"
            s.summary = summary_text[:160] + ("…" if len(summary_text) > 160 else "")
            s.detail = {"provider": provider}
        trace.activity_event("AI Summary Generated", step_key="summary")

        # ---- 9) Treatment suggestions ----------------------------------
        with trace.step("treatment") as s:
            treatments = await summary_engine.treatment(
                medicines=all_medicines, interactions=interactions,
                diseases=diseases, patient=patient_line,
            )
            s.title = f"{len(treatments)} treatment suggestion(s)"
            s.detail = {"count": len(treatments)}
        trace.activity_event("Treatment Suggestions Generated", step_key="treatment")

        # ---- 10) Follow-up suggestions ---------------------------------
        with trace.step("follow_up") as s:
            follow_ups = await summary_engine.follow_up(
                diseases=diseases, interactions=interactions, risk_level=risk_level,
            )
            s.title = f"{len(follow_ups)} follow-up suggestion(s)"
            s.detail = {"count": len(follow_ups)}
        trace.activity_event("Follow-up Suggestions Generated", step_key="follow_up")

        # ---- 11) Final medical report ----------------------------------
        report_id: str | None = None
        with trace.step("report") as s:
            report_id = await self._report(
                ocr_result_dict, all_medicines, patient_name, age, gender, diagnosis,
                interactions, clinical, warnings,
            )
            if report_id:
                s.title = "Medical report generated"
                s.summary = f"Durable report stored (id {report_id[:8]}…)."
                s.detail = {"report_id": report_id}
                sources.append("medical-report-generator")
            else:
                s.status = StepStatus.SKIPPED
                s.title = "Report not generated"
                s.summary = "Report generation was unavailable for this case."
        if report_id:
            trace.activity_event("Medical Report Generated", step_key="report")

        # ---- Assemble --------------------------------------------------
        recommendations = self._recommendations(clinical)
        references = self._references(evidence, clinical, bool(interactions), bool(diseases))

        analysis = CopilotAnalysis(
            analysis_id=uuid.uuid4().hex,
            session_id=session_id,
            created_at=utcnow(),
            duration_ms=round((time.perf_counter() - t0) * 1000.0, 1),
            ocr=ocr_summary,
            medicines=all_medicines,
            drug_interactions=interactions,
            disease_prediction=diseases,
            evidence=evidence,
            clinical_decision=clinical,
            summary=summary_text,
            treatment_suggestions=treatments,
            follow_up_suggestions=follow_ups,
            recommendations=recommendations,
            references=references,
            confidence=confidence,
            risk_level=risk_level,
            report_id=report_id,
            reasoning=trace.steps(),
            activity=trace.activity,
            warnings=warnings,
            sources=sorted(set(sources)),
        )
        logger.info(
            "Copilot workflow complete: session=%s meds=%d disease=%s risk=%s (%.0f ms)",
            session_id[:8], len(all_medicines),
            diseases[0].disease if diseases else "none", risk_level, analysis.duration_ms,
        )
        return analysis

    # ==================================================================
    # Stage implementations (each best-effort)
    # ==================================================================
    async def _run_ocr(self, image_path, trace, warnings):
        with trace.step("ocr") as s:
            from backend.ocr.pipeline import run_pipeline

            result = await asyncio.to_thread(run_pipeline, image_path)
            data = result.model_dump(mode="json")
            names = [m.get("name") for m in data.get("medicines", []) if m.get("name")]
            summary = OCRSummary(
                provider=data.get("provider", ""),
                raw_text=data.get("raw_text", ""),
                detected_medicines=names,
                fields=data.get("fields", {}) or {},
                overall_confidence=data.get("overall_confidence", 0.0),
                warnings=data.get("warnings", []) or [],
            )
            s.title = f"OCR complete ({summary.provider})"
            s.summary = f"{len(names)} medicine(s), confidence {summary.overall_confidence * 100:.0f}%."
            s.detail = {"medicines": names, "confidence": summary.overall_confidence}
            trace.activity_event("OCR Completed", detail=f"{len(names)} medicine(s)", step_key="ocr")
            return summary, data, names
        # If the step failed, the context manager set status=failed; return empties.
        warnings.append("OCR failed; continuing without extracted text.")
        return None, None, []

    async def _interactions(self, medicines, include_rag, trace, warnings):
        with trace.step("drug_interactions") as s:
            from backend.drug_interactions import analyze_medicines

            report = await analyze_medicines(
                medicines, include_rag=include_rag and settings.COPILOT_USE_RAG, persist=False,
            )
            data = report.model_dump(mode="json")
            inters = data.get("interactions") or []
            s.title = f"{len(inters)} interaction(s) found" if inters else "No interactions found"
            s.summary = "Drug-drug interaction analysis ran on the extracted medicines."
            s.detail = {"interaction_count": len(inters)}
            return data, data.get("resolved_medicines", []) or []
        warnings.append("Drug-interaction analysis was unavailable.")
        return None, []

    async def _predict_disease(self, symptoms, diagnosis, trace, warnings):
        with trace.step("disease_prediction") as s:
            hyps: list[DiseaseHypothesis] = []
            if symptoms:
                from backend.disease.service import get_service as get_disease_service

                resp = await asyncio.to_thread(get_disease_service().predict, symptoms, 5)
                hyps = [
                    DiseaseHypothesis(
                        disease=p.disease, confidence=p.confidence,
                        matched_symptoms=p.matched_symptoms, explanation=p.explanation,
                    )
                    for p in resp.predictions
                ]
            if not hyps and diagnosis:
                hyps = [DiseaseHypothesis(
                    disease=diagnosis, confidence=80.0, matched_symptoms=symptoms,
                    explanation="Diagnosis supplied with the prescription/inputs.",
                )]
            if hyps:
                s.title = f"Leading: {hyps[0].disease} ({hyps[0].confidence:.0f}%)"
                s.summary = f"{len(hyps)} candidate condition(s) ranked."
            else:
                s.status = StepStatus.SKIPPED
                s.title = "No confident prediction"
                s.summary = "The inputs did not yield a recognised disease hypothesis."
            s.detail = {"predictions": [h.model_dump(mode="json") for h in hyps]}
            return hyps
        warnings.append("Disease prediction was unavailable.")
        return []

    async def _evidence(self, diseases, diagnosis, symptoms, medicines, trace, warnings):
        with trace.step("evidence") as s:
            # Reuse the Clinical Reasoning evidence engine (RAG → normalised cards).
            from backend.clinical_reasoning.evidence_engine import get_engine as get_ev

            leading = diseases[0].disease if diseases else diagnosis
            cards, _narrative, _conf = await get_ev().gather(
                disease=leading, diagnosis=diagnosis, symptoms=symptoms,
                medicines=medicines, warnings=warnings,
            )
            out = [
                EvidenceCard(id=c.id, title=c.title, source=c.source,
                             snippet=c.snippet, relevance=c.relevance)
                for c in cards
            ]
            s.title = f"{len(out)} evidence document(s)" if out else "No evidence retrieved"
            s.summary = "Relevant passages were retrieved from the knowledge base."
            s.detail = {"count": len(out)}
            if not out:
                s.status = StepStatus.SKIPPED
            return out
        return []

    async def _clinical_decision(
        self, medicines, symptoms, diagnosis, diseases, age, gender,
        interactions, include_rag, trace, warnings,
    ):
        with trace.step("clinical_decision") as s:
            from backend.clinical_decision.schemas import ClinicalAnalysisRequest
            from backend.clinical_decision.service import analyze_clinical

            req = ClinicalAnalysisRequest(
                medicines=medicines, symptoms=symptoms,
                disease=diseases[0].disease if diseases else None,
                diagnosis=diagnosis, age=age, gender=gender,
                include_rag=include_rag, run_disease_prediction=not diseases,
                persist=False,
            )
            report = await analyze_clinical(req, interaction_report=interactions)
            data = report.model_dump(mode="json")
            s.title = f"Clinical decision · risk {data.get('risk_level', 'low')}"
            s.summary = data.get("clinical_summary", "")[:160]
            s.detail = {"risk_level": data.get("risk_level"), "confidence": data.get("confidence")}
            return data
        warnings.append("Clinical decision support was unavailable.")
        return None

    async def _report(
        self, ocr_result_dict, medicines, patient_name, age, gender, diagnosis,
        interactions, clinical, warnings,
    ):
        try:
            from backend.report_generator import get_service as get_report_service

            # Build (or reuse) an OCR-result dict for the report builder.
            payload = ocr_result_dict or self._synth_ocr_result(
                medicines, patient_name, age, gender, diagnosis,
            )
            payload = dict(payload)
            if interactions:
                payload.setdefault("drug_interactions", interactions)
            if clinical:
                payload.setdefault("clinical_report", clinical)
            return await get_report_service().generate_from_ocr(
                payload, filename="copilot-analysis", processing_time=0.0, image_src=None,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("Copilot report generation failed: %s", exc)
            warnings.append("Final medical report generation was unavailable.")
            return None

    # ==================================================================
    # Pure helpers
    # ==================================================================
    @staticmethod
    def _synth_ocr_result(medicines, patient_name, age, gender, diagnosis) -> dict:
        """Fabricate a minimal OCR-result dict for the report builder (manual path)."""
        return {
            "provider": "copilot-manual",
            "medicines": [{"raw_text": m, "name": m, "confidence": 1.0} for m in medicines],
            "fields": {
                "patient": patient_name, "age": str(age) if age is not None else None,
                "gender": gender, "diagnosis": diagnosis,
            },
            "raw_text": "",
            "overall_confidence": 1.0,
            "warnings": [],
        }

    @staticmethod
    def _patient_line(patient_name, age, gender, symptoms) -> str:
        who = []
        if patient_name:
            who.append(patient_name)
        if age is not None:
            who.append(f"{age}y")
        if gender:
            who.append(gender)
        line = "Patient: " + (", ".join(who) if who else "unknown")
        if symptoms:
            line += "; symptoms: " + ", ".join(symptoms[:8])
        return line

    @staticmethod
    def _confidence(clinical, diseases) -> float:
        if clinical and clinical.get("confidence"):
            return float(clinical["confidence"])
        if diseases:
            return float(diseases[0].confidence)
        return 50.0

    @staticmethod
    def _recommendations(clinical) -> list[Recommendation]:
        if not clinical:
            return []
        out: list[Recommendation] = []
        risk = clinical.get("risk_level", "low")
        for step in (clinical.get("recommended_next_steps") or [])[:8]:
            out.append(Recommendation(title=step, priority=risk, rationale="From clinical decision support."))
        for flag in (clinical.get("red_flags") or [])[:5]:
            out.append(Recommendation(
                title=flag.get("title", "Red flag"),
                detail=flag.get("detail", ""),
                priority=flag.get("severity", "high"),
                rationale="Urgent clinical alert.",
            ))
        return out

    @staticmethod
    def _references(evidence, clinical, used_interactions, used_model) -> list[MedicalReference]:
        refs: list[MedicalReference] = []
        for e in evidence[:8]:
            refs.append(MedicalReference(
                label=e.title, source=e.source or "Knowledge base",
                detail=(e.snippet[:160] + "…") if len(e.snippet) > 160 else e.snippet,
            ))
        if used_model:
            refs.append(MedicalReference(label="Disease-prediction model", source="Internal ML model"))
        if used_interactions:
            refs.append(MedicalReference(label="Drug-interaction dataset", source="Internal knowledge base"))
        if clinical:
            refs.append(MedicalReference(label="Clinical decision support", source="Rules + risk engine"))
        return refs


def _dedupe(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        norm = (n or "").strip()
        if norm and norm.lower() not in seen:
            seen.add(norm.lower())
            out.append(norm)
    return out


_WORKFLOW: CopilotWorkflow | None = None


def get_workflow() -> CopilotWorkflow:
    global _WORKFLOW
    if _WORKFLOW is None:
        _WORKFLOW = CopilotWorkflow()
    return _WORKFLOW
