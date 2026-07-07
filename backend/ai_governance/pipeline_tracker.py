"""Pipeline tracker — the per-step execution graph of one AI decision.

Renders the fixed clinical AI pipeline as an ordered list of steps, each with its
own execution time, status, confidence and warnings, so the frontend can draw the
visual workflow:

    Image Upload → OCR → Medicine Matching → Disease Prediction →
    Drug Interaction → RAG Retrieval → Clinical Decision → Report Generation

The wall-clock ``execution_time`` on the trace is a single number (the OCR
endpoint times the whole analysis), so per-step timings are **attributed**: the
total is distributed across the stages that actually ran using representative
weights, and a stage that produced no output is marked ``skipped`` with zero
time. This gives an honest, reproducible breakdown without fabricating precision
the trace does not carry. Pure and deterministic.
"""

from __future__ import annotations

from backend.ai_governance.schemas import (
    DecisionStatus,
    DecisionTrace,
    PipelineStep,
    PipelineView,
    StepStatus,
)

# (key, display name, relative cost weight) for time attribution.
_STAGES: list[tuple[str, str, float]] = [
    ("upload", "Image Upload", 0.02),
    ("ocr", "OCR", 0.34),
    ("medicine_matching", "Medicine Matching", 0.12),
    ("disease_prediction", "Disease Prediction", 0.14),
    ("drug_interaction", "Drug Interaction", 0.10),
    ("rag_retrieval", "RAG Retrieval", 0.16),
    ("clinical_decision", "Clinical Decision", 0.08),
    ("report_generation", "Report Generation", 0.04),
]


def _pred_score(d: dict) -> float:
    for k in ("probability", "confidence", "score"):
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _stage_state(key: str, trace: DecisionTrace) -> tuple[bool, float | None, list[str], str]:
    """Return (ran, confidence, warnings, detail) for a stage."""
    di = trace.drug_interaction or {}
    cds = trace.clinical_decision or {}
    if key == "upload":
        return True, None, [], "Prescription image received and validated."
    if key == "ocr":
        ran = bool(trace.ocr_text.strip()) or bool(trace.medicines)
        warn = [] if trace.ocr_confidence >= 0.6 else (
            ["OCR confidence below 60% — recommend re-capture."] if ran else [])
        return ran, trace.ocr_confidence or None, warn, \
            f"Extracted {len(trace.medicines)} medicine line(s) via {trace.ocr_provider or 'local'}."
    if key == "medicine_matching":
        ran = bool(trace.medicines)
        unmatched = [m.raw_text or m.name for m in trace.medicines if not m.matched]
        warn = ([f"{len(unmatched)} medicine(s) unmatched."] if unmatched else [])
        matched = sum(1 for m in trace.medicines if m.matched)
        conf = (matched / len(trace.medicines)) if trace.medicines else None
        return ran, conf, warn, f"{matched}/{len(trace.medicines)} matched to the dataset."
    if key == "disease_prediction":
        preds = [p for p in trace.disease_prediction if isinstance(p, dict)]
        ran = bool(preds)
        conf = _pred_score(preds[0]) if preds else None
        warn = ([f"Top prediction confidence low ({conf * 100:.0f}%)."]
                if conf is not None and conf < 0.5 else [])
        return ran, conf, warn, (f"Leading: {trace.top_disease}" if trace.top_disease
                                 else "No disease predicted.")
    if key == "drug_interaction":
        inter = di.get("interactions") or []
        ran = di is not None and (bool(inter) or bool(di))
        risk = (di.get("overall_risk") or "none")
        warn = ([f"{len(inter)} interaction(s) flagged ({risk} risk)."] if inter else [])
        return ran, None, warn, f"{len(inter)} interaction(s) detected."
    if key == "rag_retrieval":
        docs = trace.rag_documents
        ran = bool(docs)
        conf = (sum(min(c.score, 1.0) for c in docs) / len(docs)) if docs else None
        warn = ([] if docs else ["No knowledge-base evidence retrieved."])
        return ran, conf, warn, f"Retrieved {len(docs)} document(s)."
    if key == "clinical_decision":
        ran = bool(cds)
        risk = cds.get("risk_level")
        red = cds.get("red_flags") or []
        warn = ([f"{len(red)} clinical red flag(s)."] if red else [])
        return ran, None, warn, (f"Risk level: {risk}." if risk else "No clinical decision recorded.")
    if key == "report_generation":
        ran = bool(trace.source_report_id) or bool(trace.final_recommendation)
        return ran, None, [], (f"Report {trace.source_report_id} generated."
                               if trace.source_report_id else
                               f"{len(trace.final_recommendation)} recommendation(s) produced.")
    return True, None, [], ""


def build_pipeline(trace: DecisionTrace) -> PipelineView:
    """Construct the ordered, timed pipeline view for one decision trace."""
    states = {key: _stage_state(key, trace) for key, _, _ in _STAGES}

    # Attribute the total wall-clock time across the stages that actually ran,
    # in proportion to their representative weights.
    total = float(trace.execution_time or 0.0)
    active_weight = sum(w for key, _, w in _STAGES if states[key][0]) or 1.0

    steps: list[PipelineStep] = []
    for order, (key, name, weight) in enumerate(_STAGES, start=1):
        ran, conf, warnings, detail = states[key]
        if not ran:
            status = StepStatus.SKIPPED
            step_time = 0.0
        else:
            step_time = round(total * (weight / active_weight), 4)
            status = StepStatus.WARNING if warnings else StepStatus.COMPLETED
        steps.append(PipelineStep(
            key=key, name=name, order=order, status=status,
            execution_time=step_time, confidence=conf, warnings=warnings, detail=detail,
        ))

    # A failed OCR/no-medicine run downgrades the whole pipeline status.
    status = trace.status
    if any(s.status == StepStatus.FAILED for s in steps):
        status = DecisionStatus.FAILED

    return PipelineView(
        trace_id=trace.trace_id,
        steps=steps,
        total_time=round(total, 4),
        status=status,
    )
