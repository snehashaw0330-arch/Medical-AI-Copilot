"""Citation building for the verification engine (pure).

For each claim that the evidence actually supports, this builds a
:class:`Citation` linking the claim to its strongest evidence document with a
0-100 **citation strength** (the claim↔evidence similarity, lightly boosted by the
document's own retrieval score). It also reports **missing references** — claims
that read like factual assertions but for which no adequate citation exists.

Citation strength feeds the confidence calculator; missing references feed the
hallucination-risk estimate.
"""

from __future__ import annotations

from backend.evidence_verification.schemas import (
    Citation,
    Claim,
    ClaimSupport,
    EvidenceDocument,
)


def build(
    claims: list[Claim], evidence: list[EvidenceDocument],
) -> tuple[list[Citation], list[str]]:
    """Return ``(citations, missing_reference_claim_texts)``."""
    by_id = {e.id: e for e in evidence}
    citations: list[Citation] = []
    missing: list[str] = []

    for claim in claims:
        doc = by_id.get(claim.best_evidence_id or "")
        if claim.support == ClaimSupport.SUPPORTED and doc is not None:
            # Strength: similarity dominates, retrieval score gives a small boost.
            strength = round(min(100.0, (0.85 * claim.similarity + 0.15 * doc.retrieval_score) * 100.0), 1)
            citations.append(Citation(
                claim_id=claim.id, claim_text=claim.text,
                source=doc.source or doc.title, evidence_id=doc.id,
                snippet=claim.matched_snippet or doc.snippet, strength=strength,
            ))
        elif claim.support in (ClaimSupport.WEAK, ClaimSupport.UNSUPPORTED):
            # A factual-looking claim without a solid citation is a missing reference.
            missing.append(claim.text)

    return citations, missing
