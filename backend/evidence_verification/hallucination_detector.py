"""Claim extraction + support classification (the core of the detector).

Given an AI response and the retrieved evidence, this module:

1. splits the response into atomic **claims** (sentences), dropping boilerplate
   (questions, greetings, disclaimers) that carry no verifiable assertion;
2. builds a **claim ↔ evidence similarity matrix** — semantically via the RAG
   embedding model when available, or via a deterministic lexical fallback;
3. **classifies** each claim as supported / weak / unsupported / contradicted,
   attaching the best-matching evidence snippet and a short note.

The similarity matrix is returned so the evidence ranker and citation builder can
reuse it (computed once per verification). Everything is best-effort: if embeddings
are unavailable the lexical path still produces a full, deterministic result.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field

from backend.config import settings
from backend.evidence_verification.schemas import ClaimSupport, SimilarityMethod

logger = logging.getLogger("evidence_verification.detector")

# Lightweight English + medical stopwords for the lexical fallback.
_STOPWORDS = frozenset("""
a an the and or but if then else of to in on for with without at by from as is are was were be been being
this that these those it its their his her they them you your we our i me my he she do does did done have has had
can could should would may might must will shall not no nor so than too very just also which who whom whose what
when where why how each any all some most more less much many few own same other into over under about above below
""".split())

_NEGATIONS = frozenset(
    "not no never without cannot cant dont doesnt didnt shouldnt wont contraindicated avoid "
    "unsafe neither nor lacks lack absence".split()
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_WORD = re.compile(r"[A-Za-z0-9%\-]+")

# Lines/sentences that are not verifiable factual claims.
_BOILERPLATE = re.compile(
    r"^(please|note|disclaimer|as an ai|i am not|consult|always seek|in an emergency|"
    r"this (is|information)|hope this helps|let me know|feel free)\b",
    re.IGNORECASE,
)


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def _content_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _STOPWORDS and len(t) > 2}


def split_into_claims(text: str) -> list[str]:
    """Split a response into atomic, verifiable claims (sentences)."""
    if not text or not text.strip():
        return []
    # Normalise bullet points / newlines into sentence boundaries.
    normalised = re.sub(r"[\r\n]+", " ", text)
    normalised = re.sub(r"\s*[-•*]\s+", ". ", normalised)
    raw = _SENTENCE_SPLIT.split(normalised)
    claims: list[str] = []
    for s in raw:
        s = s.strip(" -•*\t")
        if len(s) < 12:                      # too short to be a claim
            continue
        if s.endswith("?"):                  # questions are not assertions
            continue
        if _BOILERPLATE.match(s):
            continue
        if len(_content_tokens(s)) < 2:      # no substantive content
            continue
        claims.append(s)
    return claims


def _split_sentences(text: str) -> list[str]:
    out = [s.strip() for s in _SENTENCE_SPLIT.split(re.sub(r"[\r\n]+", " ", text or "")) if s.strip()]
    return out or ([text.strip()] if text and text.strip() else [])


# --------------------------------------------------------------------------
# Similarity
# --------------------------------------------------------------------------
def _lexical_sim(claim_tokens: set[str], sent_tokens: set[str]) -> float:
    """Containment-weighted lexical similarity in 0..1.

    Rewards evidence that *covers* the claim's content tokens (good for support
    detection), blended with Jaccard to penalise over-broad matches.
    """
    if not claim_tokens or not sent_tokens:
        return 0.0
    inter = claim_tokens & sent_tokens
    if not inter:
        return 0.0
    containment = len(inter) / len(claim_tokens)
    union = claim_tokens | sent_tokens
    jaccard = len(inter) / len(union)
    return round(0.7 * containment + 0.3 * jaccard, 4)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    # RAG embeddings are already unit-normalised, but guard anyway.
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


@dataclass
class SimilarityMatrix:
    """claims × evidence-docs similarity, with the best matching snippet."""

    method: SimilarityMethod
    doc_sim: list[list[float]] = field(default_factory=list)      # [claim][doc]
    best_snippet: list[list[str]] = field(default_factory=list)   # [claim][doc]

    def best_doc(self, claim_idx: int) -> tuple[int, float, str]:
        """Return (doc_idx, similarity, snippet) of the best doc for a claim."""
        row = self.doc_sim[claim_idx] if claim_idx < len(self.doc_sim) else []
        if not row:
            return -1, 0.0, ""
        best = max(range(len(row)), key=lambda j: row[j])
        return best, row[best], self.best_snippet[claim_idx][best]


async def build_similarity(claims: list[str], evidence_texts: list[str]) -> SimilarityMatrix:
    """Build the claim×evidence similarity matrix.

    When embeddings are available the semantic score is **blended** with lexical
    content-containment: this is what stops a hallucinated claim from being marked
    "supported" purely because it is on the same *topic* as the evidence (MiniLM
    sentence embeddings give same-topic sentences a high baseline cosine even when
    the specific assertion is absent). A claim whose distinctive terms do not
    appear in the evidence is penalised down to weak/unsupported.
    """
    n, m = len(claims), len(evidence_texts)
    if n == 0 or m == 0:
        return SimilarityMatrix(method=SimilarityMethod.LEXICAL)

    # Split each evidence doc into sentences (more precise support matching).
    doc_sentences: list[list[str]] = [_split_sentences(t)[:12] for t in evidence_texts]

    lexical = _lexical_matrix(claims, doc_sentences)
    if settings.VERIFICATION_USE_EMBEDDINGS:
        semantic = await _try_semantic(claims, doc_sentences)
        if semantic is not None:
            return _blend(semantic, lexical)
    return lexical


def _blend(semantic: SimilarityMatrix, lexical: SimilarityMatrix) -> SimilarityMatrix:
    """Blend semantic cosine (0.6) with lexical containment (0.4), keeping the
    semantic best-sentence snippet. Grounds topical similarity in actual term
    overlap so hallucinations aren't rewarded for being on-topic."""
    doc_sim: list[list[float]] = []
    best_snip: list[list[str]] = []
    for ci in range(len(semantic.doc_sim)):
        row, snips = [], []
        for di in range(len(semantic.doc_sim[ci])):
            sem = semantic.doc_sim[ci][di]
            lex = lexical.doc_sim[ci][di] if ci < len(lexical.doc_sim) and di < len(lexical.doc_sim[ci]) else 0.0
            row.append(round(0.6 * sem + 0.4 * lex, 4))
            snips.append(semantic.best_snippet[ci][di] or (lexical.best_snippet[ci][di] if ci < len(lexical.best_snippet) else ""))
        doc_sim.append(row)
        best_snip.append(snips)
    return SimilarityMatrix(SimilarityMethod.SEMANTIC, doc_sim, best_snip)


async def _try_semantic(claims: list[str], doc_sentences: list[list[str]]) -> SimilarityMatrix | None:
    """Embedding-based similarity; returns None if the model is unavailable."""
    try:
        from backend.rag.embedding import get_embedder

        embedder = get_embedder()
        # Flatten evidence sentences with a map back to their doc.
        flat: list[str] = []
        owner: list[int] = []
        for di, sents in enumerate(doc_sentences):
            for s in sents:
                flat.append(s)
                owner.append(di)
        if not flat:
            return None
        claim_vecs = await embedder.aembed_texts(claims)
        sent_vecs = await embedder.aembed_texts(flat)
    except Exception as exc:  # noqa: BLE001 — fall back to lexical
        logger.info("Semantic similarity unavailable, using lexical: %s", exc)
        return None

    m = len(doc_sentences)
    doc_sim = [[0.0] * m for _ in claims]
    best_snip = [[""] * m for _ in claims]
    for ci, cvec in enumerate(claim_vecs):
        for si, svec in enumerate(sent_vecs):
            sim = _cosine(cvec, svec)
            di = owner[si]
            if sim > doc_sim[ci][di]:
                doc_sim[ci][di] = round(max(0.0, sim), 4)
                best_snip[ci][di] = flat[si]
    return SimilarityMatrix(SimilarityMethod.SEMANTIC, doc_sim, best_snip)


def _lexical_matrix(claims: list[str], doc_sentences: list[list[str]]) -> SimilarityMatrix:
    m = len(doc_sentences)
    doc_sim = [[0.0] * m for _ in claims]
    best_snip = [[""] * m for _ in claims]
    claim_toks = [_content_tokens(c) for c in claims]
    for di, sents in enumerate(doc_sentences):
        sent_toks = [(_content_tokens(s), s) for s in sents]
        for ci, ctoks in enumerate(claim_toks):
            best, snip = 0.0, ""
            for stoks, s in sent_toks:
                sim = _lexical_sim(ctoks, stoks)
                if sim > best:
                    best, snip = sim, s
            doc_sim[ci][di] = best
            best_snip[ci][di] = snip
    return SimilarityMatrix(SimilarityMethod.LEXICAL, doc_sim, best_snip)


# --------------------------------------------------------------------------
# Contradiction heuristic
# --------------------------------------------------------------------------
def _negated(text: str) -> bool:
    toks = set(_tokens(text))
    return bool(toks & _NEGATIONS) or bool(re.search(r"\bno\s+\w+", text.lower()))


def is_contradiction(claim: str, evidence_snippet: str) -> bool:
    """Heuristic: high overlap but opposite negation polarity ⇒ contradiction."""
    if not evidence_snippet:
        return False
    shared = _content_tokens(claim) & _content_tokens(evidence_snippet)
    if len(shared) < 2:
        return False
    return _negated(claim) != _negated(evidence_snippet)


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------
@dataclass
class ClaimVerdict:
    support: ClaimSupport
    similarity: float
    best_doc: int
    snippet: str
    note: str


def classify(
    claims: list[str], matrix: SimilarityMatrix,
    *, support_th: float | None = None, weak_th: float | None = None,
) -> list[ClaimVerdict]:
    """Classify every claim's support level against the evidence."""
    # Lexical scores run lower than semantic cosine — scale thresholds down.
    if matrix.method == SimilarityMethod.SEMANTIC:
        s_th = settings.VERIFICATION_SUPPORT_THRESHOLD if support_th is None else support_th
        w_th = settings.VERIFICATION_WEAK_THRESHOLD if weak_th is None else weak_th
    else:
        s_th, w_th = 0.42, 0.20

    verdicts: list[ClaimVerdict] = []
    for ci, _claim in enumerate(claims):
        doc, sim, snip = matrix.best_doc(ci)
        if doc >= 0 and is_contradiction(claims[ci], snip) and sim >= w_th:
            verdicts.append(ClaimVerdict(
                ClaimSupport.CONTRADICTED, sim, doc, snip,
                "Evidence appears to state the opposite of this claim.",
            ))
        elif sim >= s_th:
            verdicts.append(ClaimVerdict(
                ClaimSupport.SUPPORTED, sim, doc, snip,
                "Directly supported by the retrieved evidence.",
            ))
        elif sim >= w_th:
            verdicts.append(ClaimVerdict(
                ClaimSupport.WEAK, sim, doc, snip,
                "Only partially / indirectly supported by the evidence.",
            ))
        else:
            verdicts.append(ClaimVerdict(
                ClaimSupport.UNSUPPORTED, sim, max(doc, -1), snip,
                "No supporting evidence was found for this claim.",
            ))
    return verdicts
