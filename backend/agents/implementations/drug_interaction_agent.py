"""Drug Interaction Agent — interactions, risk, contraindications & warnings.

Delegates to the existing Drug Interaction Analysis service. RAG is disabled here
(``include_rag=False``) so the Knowledge Agent stays the single RAG gateway.
"""

from __future__ import annotations

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys


class DrugInteractionAgent(BaseAgent):
    name = ac.DRUG_INTERACTION
    title = "Drug Interaction Agent"
    description = "Detect drug-drug interactions, risk level, contraindications, pregnancy and food warnings."
    reads = (MemoryKeys.MEDICINES,)
    writes = (MemoryKeys.INTERACTIONS,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        medicines = await ctx.get(MemoryKeys.MEDICINES, {})
        names = (medicines or {}).get("names", [])
        if not names:
            return AgentOutcome.skipped("No medicines available for interaction analysis.")

        from backend.drug_interactions import analyze_medicines

        report = await analyze_medicines(names, include_rag=False, persist=False)
        data = report.model_dump(mode="json")
        interactions = data.get("interactions", []) or []
        data["interaction_count"] = len(interactions)
        await ctx.set(MemoryKeys.INTERACTIONS, data)

        # Confidence = how much of the medicine list we could resolve in the KB.
        resolved = len(data.get("resolved_medicines", []) or [])
        total = max(1, len(names))
        confidence = round(resolved / total, 3)
        risk = data.get("overall_risk", "none")
        summary = (f"{len(interactions)} interaction(s) found; overall risk: {risk}."
                   if names else "No interactions to report.")
        return AgentOutcome(summary=summary, confidence=confidence,
                            details={"overall_risk": risk, "interaction_count": len(interactions)})

    async def health_check(self) -> tuple[bool, str]:
        try:
            import asyncio

            from backend.drug_interactions.service import build_source

            source = build_source()
            knowledge = await asyncio.to_thread(source.load)
            return True, f"Interaction dataset loaded ({len(knowledge.pairs)} rule(s))."
        except Exception as exc:  # noqa: BLE001
            return False, f"Interaction dataset failed to load: {exc}"
