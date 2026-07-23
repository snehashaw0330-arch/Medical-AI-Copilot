"""Evidence Verification Agent — checks the Clinical Decision Agent's summary
against the evidence the Knowledge Agent retrieved.

Delegates entirely to the existing Evidence Verification Engine
(`backend.evidence_verification`): it does not re-retrieve evidence or
re-implement claim scoring — it hands the clinical summary and the Knowledge
Agent's already-retrieved chunks straight to `verify_response()`, which
breaks the summary into claims, scores each against the supplied evidence and
returns evidence coverage, citation strength, a hallucination-risk category
and a confidence score. This is what closes the loop on hallucination
reduction: nothing the pipeline concludes reaches the Report Agent unverified.

Runs concurrently with the Explainability Agent (same stage) — both only read
Clinical/Knowledge output and don't depend on each other.
"""

from __future__ import annotations

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys


class EvidenceVerificationAgent(BaseAgent):
    name = ac.EVIDENCE_VERIFICATION
    title = "Evidence Verification Agent"
    description = "Verify the clinical assessment against retrieved evidence — hallucination risk, citations and confidence."
    reads = (MemoryKeys.CLINICAL, MemoryKeys.KNOWLEDGE, MemoryKeys.MEDICINES, MemoryKeys.DISEASE)
    writes = (MemoryKeys.EVIDENCE_VERIFICATION,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        clinical = await ctx.get(MemoryKeys.CLINICAL, {}) or {}
        knowledge = await ctx.get(MemoryKeys.KNOWLEDGE, {}) or {}
        medicines = await ctx.get(MemoryKeys.MEDICINES, {}) or {}
        disease = await ctx.get(MemoryKeys.DISEASE, {}) or {}

        response_text = clinical.get("summary") or ""
        chunks = knowledge.get("chunks") or []
        if not response_text or not chunks:
            return AgentOutcome.skipped(
                "No clinical summary or retrieved evidence available to verify."
            )

        names = medicines.get("names", [])
        preds = disease.get("predictions", [])
        topic = preds[0]["disease"] if preds else (", ".join(names[:4]) if names else "the assessment")
        question = f"What is the clinical assessment and risk for {topic}?"

        from backend.evidence_verification.schemas import EvidenceInput
        from backend.evidence_verification.service import verify_response

        evidence = [
            EvidenceInput(text=c.get("text", ""), source=c.get("source", ""),
                          score=float(c.get("score") or 0.0))
            for c in chunks if c.get("text")
        ]

        result = await verify_response(
            question=question, response=response_text, source_module="agents",
            evidence=evidence, persist=False,
        )
        data = result.model_dump(mode="json")
        await ctx.set(MemoryKeys.EVIDENCE_VERIFICATION, data)

        metrics = data.get("metrics", {})
        confidence = metrics.get("confidence")
        confidence = (confidence / 100.0) if isinstance(confidence, (int, float)) else None
        risk = metrics.get("hallucination_risk", "medium")
        summary = (
            f"Hallucination risk: {risk}; evidence coverage "
            f"{metrics.get('evidence_coverage', 0):.0f}%."
        )
        return AgentOutcome(
            summary=summary, confidence=confidence,
            details={
                "hallucination_risk": risk,
                "evidence_coverage": metrics.get("evidence_coverage"),
                "unsupported_claims": len(data.get("unsupported_claims", []) or []),
            },
        )

    async def health_check(self) -> tuple[bool, str]:
        try:
            from backend.rag.retriever import get_retriever

            ok = get_retriever().available()
            return ok, ("RAG evidence source reachable." if ok
                        else "RAG embedder/vector store unavailable — verification degrades to skipped.")
        except Exception as exc:  # noqa: BLE001
            return False, f"RAG evidence source check failed: {exc}"
