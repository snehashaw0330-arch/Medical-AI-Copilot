"""The verification orchestrator (async, best-effort).

Given a question, an AI-generated response and the retrieved evidence, this runs
the verification pipeline end to end:

    split response into claims
        → build claim↔evidence similarity (semantic, else lexical)
        → classify each claim (supported / weak / unsupported / contradicted)
        → rank evidence + build citations
        → compute coverage, citation strength, hallucination risk & confidence
        → assemble the VerificationResult

It is pure orchestration over the other engines in this module — no I/O of its own
(the RAG retrieval / generation lives in ``service.py``). Everything is
best-effort: an empty response or empty evidence still yields a well-formed,
honest result rather than an error.
"""

from __future__ import annotations

import logging

from backend.evidence_verification import (
    citation_builder,
    confidence_calculator,
    evidence_ranker,
    hallucination_detector as detector,
)
from backend.evidence_verification.schemas import (
    Claim,
    ClaimSupport,
    Contradiction,
    EvidenceInput,
    SimilarityMethod,
    VerificationResult,
)

logger = logging.getLogger("evidence_verification.engine")


class VerificationEngine:
    """Runs the claim-level verification pipeline over one response."""

    async def verify(
        self,
        *,
        question: str,
        response: str,
        evidence: list[EvidenceInput],
        retrieval_confidence: float,
        source_module: str = "chat",
        generated: bool = False,
    ) -> VerificationResult:
        warnings: list[str] = []

        evidence_texts = [e.text for e in evidence]
        evidence_sources = [e.source for e in evidence]
        evidence_scores = [e.score for e in evidence]

        # 1) Extract atomic claims.
        claim_texts = detector.split_into_claims(response or "")
        if not evidence:
            warnings.append("No evidence was available; every claim is treated as unverified.")

        # 2) Similarity matrix (semantic, else lexical).
        matrix = await detector.build_similarity(claim_texts, evidence_texts)

        # 3) Classify each claim.
        verdicts = detector.classify(claim_texts, matrix)
        claims: list[Claim] = []
        for i, (text, v) in enumerate(zip(claim_texts, verdicts)):
            best_id = f"ev-{v.best_doc + 1}" if v.best_doc is not None and v.best_doc >= 0 else None
            best_src = evidence_sources[v.best_doc] if (v.best_doc is not None and 0 <= v.best_doc < len(evidence_sources)) else None
            claims.append(Claim(
                id=f"c{i + 1}", text=text, order=i, support=v.support,
                similarity=round(v.similarity, 4), best_evidence_id=best_id,
                best_source=best_src, matched_snippet=v.snippet, note=v.note,
            ))

        # 4) Rank evidence + annotate which claims each doc supports.
        ranked = evidence_ranker.rank(
            evidence_texts, evidence_sources, evidence_scores, claims, matrix,
        )

        # 5) Citations + missing references.
        citations, missing = citation_builder.build(claims, ranked)

        # 6) Contradictions (surfaced as their own list too).
        contradictions: list[Contradiction] = []
        for c in claims:
            if c.support == ClaimSupport.CONTRADICTED:
                contradictions.append(Contradiction(
                    claim_id=c.id, claim_text=c.text,
                    evidence_id=c.best_evidence_id or "",
                    source=c.best_source or "", evidence_snippet=c.matched_snippet,
                    explanation="The evidence appears to state the opposite of this claim.",
                ))

        # 7) Metrics + confidence.
        metrics, breakdown, verdict = confidence_calculator.compute(
            claims=claims, citations=citations, evidence=ranked,
            missing_reference_count=len(missing), retrieval_confidence=retrieval_confidence,
        )

        unsupported_texts = [c.text for c in claims if c.support == ClaimSupport.UNSUPPORTED]

        result = VerificationResult(
            question=question, response=response or "", source_module=source_module,
            method=matrix.method if claim_texts else SimilarityMethod.LEXICAL,
            generated=generated, metrics=metrics, confidence_breakdown=breakdown,
            claims=claims, evidence=ranked, citations=citations,
            contradictions=contradictions, unsupported_claims=unsupported_texts,
            missing_references=missing, verdict=verdict, warnings=warnings,
            sources=sorted({e.source for e in ranked if e.source}),
        )
        logger.info(
            "Verification: %d claim(s), coverage=%.0f%%, risk=%s, conf=%.0f (%s)",
            metrics.total_claims, metrics.evidence_coverage,
            metrics.hallucination_risk.value, metrics.confidence, result.method.value,
        )
        return result


_ENGINE: VerificationEngine | None = None


def get_engine() -> VerificationEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = VerificationEngine()
    return _ENGINE
