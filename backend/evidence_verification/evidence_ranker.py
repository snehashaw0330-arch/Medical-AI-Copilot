"""Evidence ranking for the verification engine (pure).

Turns the retrieved evidence chunks + the claim×evidence similarity matrix into
ranked :class:`EvidenceDocument`s, each annotated with:

* its **relevance to the response** (how strongly its content matches the claims),
  blended with its original retrieval score, and
* the **claims it supports** (so the UI can show which statements each document
  backs up).

Ranking by response-relevance — not just the raw retrieval score — surfaces the
documents that actually did the verifying work.
"""

from __future__ import annotations

from backend.evidence_verification.hallucination_detector import SimilarityMatrix
from backend.evidence_verification.schemas import Claim, EvidenceDocument

_WEAK_LINK = 0.20   # min similarity for a doc to be listed as "supports" a claim


def _title(source: str, index: int) -> str:
    if source and source.lower() not in ("", "unknown"):
        # Use the file stem as a readable title.
        base = source.replace("\\", "/").split("/")[-1]
        return base.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title() or f"Document {index + 1}"
    return f"Document {index + 1}"


def rank(
    evidence_texts: list[str],
    evidence_sources: list[str],
    evidence_scores: list[float],
    claims: list[Claim],
    matrix: SimilarityMatrix,
) -> list[EvidenceDocument]:
    """Build ranked evidence documents annotated with the claims they support."""
    m = len(evidence_texts)
    docs: list[EvidenceDocument] = []

    for di in range(m):
        # Relevance to the response = the strongest claim match this doc achieved.
        col = [matrix.doc_sim[ci][di] for ci in range(len(claims)) if di < len(matrix.doc_sim[ci])] \
            if matrix.doc_sim else []
        relevance = max(col) if col else 0.0

        # Which claims does this doc back up (it was their best match, weakly+)?
        supports: list[str] = []
        for ci, claim in enumerate(claims):
            if ci >= len(matrix.doc_sim):
                continue
            best_doc = max(range(m), key=lambda j: matrix.doc_sim[ci][j]) if m else -1
            if best_doc == di and matrix.doc_sim[ci][di] >= _WEAK_LINK:
                supports.append(claim.id)

        retrieval = float(evidence_scores[di]) if di < len(evidence_scores) else 0.0
        # Blend response-relevance (0.7) with the original retrieval score (0.3).
        blended = round(0.7 * relevance + 0.3 * retrieval, 4)

        text = evidence_texts[di]
        docs.append(EvidenceDocument(
            id=f"ev-{di + 1}",
            title=_title(evidence_sources[di] if di < len(evidence_sources) else "", di),
            source=evidence_sources[di] if di < len(evidence_sources) else "",
            snippet=(text[:600] + "…") if len(text) > 600 else text,
            retrieval_score=round(retrieval, 4),
            relevance=blended,
            supports_claims=supports,
        ))

    docs.sort(key=lambda d: d.relevance, reverse=True)
    return docs
