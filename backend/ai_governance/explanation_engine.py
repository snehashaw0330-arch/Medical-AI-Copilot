"""Explanation engine — the "why" behind every sub-decision of a trace.

Enterprise healthcare AI must be *explainable*: a clinician has to be able to
see why the OCR read a word, why a medicine was matched, why one disease was
chosen and another rejected, why an interaction was flagged, why each RAG
document was retrieved and why the final recommendation was produced.

This is a **pure, deterministic** transform: it consumes a :class:`DecisionTrace`
and derives grounded, human-readable rationales from the evidence already present
in the trace (match scores, confidences, prediction probabilities, retrieval
scores). It invents nothing — every rationale points back at concrete numbers so
the explanation is reproducible and auditable.
"""

from __future__ import annotations

from backend.ai_governance.schemas import (
    DecisionTrace,
    ExplanationItem,
    ExplanationReport,
)


def _pct(x: float | None) -> str:
    try:
        return f"{float(x) * 100:.0f}%"
    except (TypeError, ValueError):
        return "n/a"


def _explain_ocr(trace: DecisionTrace) -> list[ExplanationItem]:
    items: list[ExplanationItem] = []
    for m in trace.medicines[:12]:
        raw = (m.raw_text or m.name or "").strip()
        if not raw:
            continue
        conf = m.confidence or 0.0
        if conf >= 0.85:
            band = "high recognition confidence"
        elif conf >= 0.6:
            band = "acceptable recognition confidence"
        else:
            band = "low recognition confidence (manual verification advised)"
        items.append(ExplanationItem(
            subject=raw,
            decision="selected",
            rationale=(f"The OCR engine read '{raw}' with {_pct(conf)} confidence "
                       f"— {band}."),
            evidence=[f"ocr_provider={trace.ocr_provider or 'local'}",
                      f"row_confidence={_pct(conf)}"],
            confidence=conf,
        ))
    return items


def _explain_medicines(trace: DecisionTrace) -> list[ExplanationItem]:
    items: list[ExplanationItem] = []
    for m in trace.medicines[:12]:
        if not (m.name or m.raw_text):
            continue
        cands = m.candidates or []
        top = cands[0] if cands else None
        if m.matched and m.name:
            best_score = (top or {}).get("score")
            rationale = (
                f"'{m.raw_text or m.name}' matched to '{m.name}' — the highest-"
                f"scoring candidate in the medicine dataset"
                + (f" (match score {best_score})." if best_score is not None else ".")
            )
            runner = cands[1] if len(cands) > 1 else None
            evidence = [f"top_candidate={m.name}"]
            if runner:
                evidence.append(
                    f"runner_up={runner.get('name')} (score {runner.get('score')})"
                )
            items.append(ExplanationItem(
                subject=m.name, decision="selected", rationale=rationale,
                evidence=evidence, confidence=m.confidence,
            ))
        else:
            items.append(ExplanationItem(
                subject=(m.name or m.raw_text or "unknown"),
                decision="unmatched",
                rationale=("No dataset entry scored above the match threshold, so no "
                           "medicine was fabricated — the term is surfaced for manual review."),
                evidence=[f"candidates_considered={len(cands)}"],
                confidence=m.confidence,
            ))
    return items


def _sorted_predictions(trace: DecisionTrace) -> list[dict]:
    def score(d: dict) -> float:
        for k in ("probability", "confidence", "score"):
            v = d.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return 0.0

    preds = [p for p in (trace.disease_prediction or []) if isinstance(p, dict)]
    return sorted(preds, key=score, reverse=True)


def _pred_name(d: dict) -> str:
    return str(d.get("disease") or d.get("name") or d.get("label") or "condition")


def _pred_score(d: dict) -> float:
    for k in ("probability", "confidence", "score"):
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _explain_disease(trace: DecisionTrace) -> tuple[list[ExplanationItem], list[ExplanationItem]]:
    preds = _sorted_predictions(trace)
    selected: list[ExplanationItem] = []
    rejected: list[ExplanationItem] = []
    if not preds:
        return selected, rejected

    top = preds[0]
    top_name, top_score = _pred_name(top), _pred_score(top)
    runner_up = preds[1] if len(preds) > 1 else None
    margin = top_score - (_pred_score(runner_up) if runner_up else 0.0)
    selected.append(ExplanationItem(
        subject=top_name,
        decision="selected",
        rationale=(f"'{top_name}' was chosen as the leading prediction with the highest "
                   f"model probability ({_pct(top_score)})"
                   + (f", ahead of '{_pred_name(runner_up)}' by {_pct(margin)}."
                      if runner_up else ".")),
        evidence=[f"probability={_pct(top_score)}",
                  f"candidates={len(preds)}"],
        confidence=top_score,
    ))
    for d in preds[1:5]:
        rejected.append(ExplanationItem(
            subject=_pred_name(d),
            decision="rejected",
            rationale=(f"'{_pred_name(d)}' scored {_pct(_pred_score(d))}, below the leading "
                       f"'{top_name}' ({_pct(top_score)}), so it was not selected."),
            evidence=[f"probability={_pct(_pred_score(d))}"],
            confidence=_pred_score(d),
        ))
    return selected, rejected


def _explain_interactions(trace: DecisionTrace) -> list[ExplanationItem]:
    di = trace.drug_interaction or {}
    items: list[ExplanationItem] = []
    for it in (di.get("interactions") or [])[:8]:
        if not isinstance(it, dict):
            continue
        meds = it.get("medicines") or it.get("pair") or []
        pair = " + ".join(str(x) for x in meds) if isinstance(meds, list) else str(meds)
        severity = it.get("severity") or it.get("clinical_risk") or "unspecified"
        mechanism = it.get("mechanism") or it.get("description") or it.get("effect") or ""
        items.append(ExplanationItem(
            subject=pair or "medicine pair",
            decision="flagged",
            rationale=(f"Flagged as a {severity} interaction"
                       + (f": {mechanism}" if mechanism else
                          " based on a known drug–drug interaction in the dataset.")),
            evidence=[f"severity={severity}"] + ([f"source={it.get('source')}"]
                                                 if it.get("source") else []),
        ))
    return items


def _explain_rag(trace: DecisionTrace) -> list[ExplanationItem]:
    items: list[ExplanationItem] = []
    for c in trace.rag_documents[:8]:
        snippet = (c.text or "").strip().replace("\n", " ")
        if len(snippet) > 160:
            snippet = snippet[:160] + "…"
        items.append(ExplanationItem(
            subject=c.source or "knowledge-base",
            decision="retrieved",
            rationale=(f"Retrieved because its semantic similarity to the query "
                       f"({c.score:.2f}) ranked it among the top matches in the "
                       f"knowledge base."),
            evidence=[f"similarity={c.score:.2f}"] + ([snippet] if snippet else []),
            confidence=min(max(c.score, 0.0), 1.0) if c.score <= 1 else None,
        ))
    return items


def _explain_recommendation(trace: DecisionTrace) -> list[ExplanationItem]:
    items: list[ExplanationItem] = []
    n_docs = len(trace.rag_documents)
    n_flags = len((trace.drug_interaction or {}).get("interactions") or [])
    basis = []
    if trace.top_disease:
        basis.append(f"the leading prediction ({trace.top_disease})")
    if n_flags:
        basis.append(f"{n_flags} flagged interaction(s)")
    if n_docs:
        basis.append(f"{n_docs} supporting knowledge-base document(s)")
    basis_txt = ", ".join(basis) if basis else "the analysed prescription"
    for rec in (trace.final_recommendation or [])[:8]:
        items.append(ExplanationItem(
            subject=rec[:80],
            decision="generated",
            rationale=f"Derived from {basis_txt}.",
            evidence=[f"grounded_in_documents={n_docs}",
                      f"interaction_flags={n_flags}"],
            confidence=trace.confidence or None,
        ))
    return items


def explain(trace: DecisionTrace) -> ExplanationReport:
    """Produce the full explainability report for one decision trace."""
    disease_selected, disease_rejected = _explain_disease(trace)
    report = ExplanationReport(
        trace_id=trace.trace_id,
        ocr=_explain_ocr(trace),
        medicine_matching=_explain_medicines(trace),
        disease_selected=disease_selected,
        disease_rejected=disease_rejected,
        drug_interactions=_explain_interactions(trace),
        rag_retrieval=_explain_rag(trace),
        final_recommendation=_explain_recommendation(trace),
    )
    report.summary = (
        f"Decision {trace.trace_id} is explained across {len(report.ocr)} OCR reads, "
        f"{len(report.medicine_matching)} medicine matches, "
        f"{len(report.disease_selected) + len(report.disease_rejected)} disease candidates, "
        f"{len(report.drug_interactions)} interaction flags and "
        f"{len(report.rag_retrieval)} retrieved documents."
    )
    return report
