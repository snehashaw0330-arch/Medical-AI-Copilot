"""Explainability Agent — explains WHY each conclusion was reached.

Reads every prior agent's output from shared memory and produces a structured,
human-readable rationale: which symptoms drove the disease prediction, why
interactions were flagged, which evidence was retrieved, and how the confidence
was derived. The deterministic explanation is grounded in the actual data; the
injected LLM (offline-safe) optionally composes a short overall narrative — it
never invents facts, it only phrases the grounded ones.
"""

from __future__ import annotations

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys


class ExplainabilityAgent(BaseAgent):
    name = ac.EXPLAINABILITY
    title = "Explainability Agent"
    description = "Explain WHY each conclusion was reached, with the evidence and confidence behind it."
    reads = (MemoryKeys.DISEASE, MemoryKeys.MEDICINES, MemoryKeys.INTERACTIONS,
             MemoryKeys.KNOWLEDGE, MemoryKeys.CLINICAL)
    writes = (MemoryKeys.EXPLANATION,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        disease = await ctx.get(MemoryKeys.DISEASE, {}) or {}
        medicines = await ctx.get(MemoryKeys.MEDICINES, {}) or {}
        interactions = await ctx.get(MemoryKeys.INTERACTIONS, {}) or {}
        knowledge = await ctx.get(MemoryKeys.KNOWLEDGE, {}) or {}
        clinical = await ctx.get(MemoryKeys.CLINICAL, {}) or {}

        reasons: list[dict] = []

        # Disease reasoning.
        preds = disease.get("predictions", [])
        if preds:
            top = preds[0]
            matched = ", ".join(top.get("matched_symptoms", [])[:4]) or "the reported symptoms"
            reasons.append({
                "conclusion": f"Predicted condition: {top['disease']} ({top['confidence']:.0f}%)",
                "why": f"Driven by {matched}. Model confidence level: {disease.get('confidence_level', 'n/a')}.",
                "evidence": "disease-prediction model",
            })

        # Medicine reasoning.
        names = medicines.get("names", [])
        if names:
            reasons.append({
                "conclusion": f"{len(names)} medicine(s) identified: {', '.join(names[:5])}",
                "why": "Resolved against the medicine dataset via fuzzy/phonetic matching; "
                       "alternatives and generics were derived from listed substitutes.",
                "evidence": "medicine dataset",
            })

        # Interaction reasoning.
        inter = interactions.get("interactions", [])
        if inter:
            pairs = [" + ".join(i.get("medicines", [])) for i in inter[:3]]
            reasons.append({
                "conclusion": f"Overall interaction risk: {interactions.get('overall_risk', 'none')}",
                "why": "Flagged because these pairs co-occur with documented interactions: "
                       + "; ".join(pairs) + ".",
                "evidence": "drug-interaction dataset",
            })

        # Evidence retrieval reasoning.
        sources = knowledge.get("sources", [])
        if sources:
            reasons.append({
                "conclusion": "Evidence-based context retrieved",
                "why": f"Retrieved {len(sources)} passage(s) from the knowledge base to ground the assessment.",
                "evidence": ", ".join(sources),
            })

        # Clinical reasoning.
        if clinical.get("risk_level"):
            reasons.append({
                "conclusion": f"Clinical risk level: {clinical['risk_level']}",
                "why": clinical.get("summary") or "Synthesised from the medicines, condition and interactions.",
                "evidence": "clinical-rules engine",
            })

        if not reasons:
            return AgentOutcome.skipped("No conclusions available to explain.")

        # Optional LLM narrative (offline-safe) grounded in the reasons above.
        facts = "\n".join(f"- {r['conclusion']}: {r['why']}" for r in reasons)
        try:
            narrative = await ctx.llm.asummarize(
                facts, instruction="Explain these medical findings plainly for a clinician:")
        except Exception:  # noqa: BLE001 — narrative is optional
            narrative = facts

        await ctx.set(MemoryKeys.EXPLANATION, {
            "reasons": reasons,
            "narrative": narrative,
            "llm_provider": ctx.llm.name,
        })
        return AgentOutcome(
            summary=f"Explained {len(reasons)} conclusion(s).",
            confidence=None,
            details={"reason_count": len(reasons), "llm_provider": ctx.llm.name},
        )
