"""Medicine Agent — detection, spelling correction, dosage + alternatives.

Reads the medicines OCR detected (or names supplied directly), then delegates to
the existing Medicine Recommendation service for canonical resolution, alternatives
and generic equivalents. RAG is intentionally *not* used here (``include_rag=
False``) — the Knowledge Agent is the single gateway to the knowledge base.
"""

from __future__ import annotations

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys
from backend.agents.security import sanitize_tokens


class MedicineAgent(BaseAgent):
    name = ac.MEDICINE
    title = "Medicine Agent"
    description = "Detect medicines, correct spelling via fuzzy matching, extract dosage and find alternatives."
    reads = (MemoryKeys.OCR, MemoryKeys.INPUTS)
    writes = (MemoryKeys.MEDICINES,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        ocr = await ctx.get(MemoryKeys.OCR, {})
        inputs = await ctx.get(MemoryKeys.INPUTS, {})

        # Prefer OCR-detected medicines (they carry dosage/frequency); otherwise
        # use names supplied directly by the caller.
        detected: list[dict] = []
        if ocr and ocr.get("medicines"):
            for m in ocr["medicines"]:
                detected.append({
                    "name": m.get("name") or m.get("raw_text"),
                    "dosage": m.get("dosage"),
                    "frequency": m.get("frequency_expanded") or m.get("frequency"),
                    "duration": m.get("duration"),
                    "confidence": m.get("confidence"),
                })
        else:
            for name in sanitize_tokens(inputs.get("medicines"), max_items=ctx.config.max_medicines):
                detected.append({"name": name, "dosage": None, "frequency": None,
                                 "duration": None, "confidence": None})

        names = [d["name"] for d in detected if d.get("name")]
        if not names:
            return AgentOutcome.skipped("No medicines detected to analyse.")
        names = names[: ctx.config.max_medicines]

        # Delegate to the recommendation engine for alternatives (no RAG here).
        recommendations: dict = {}
        try:
            from backend.medicine_recommendation import recommend_medicines
            from backend.medicine_recommendation.schemas import MedicineRecommendRequest

            report = await recommend_medicines(MedicineRecommendRequest(
                medicines=names, include_rag=False, persist=False,
            ))
            recommendations = report.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 — alternatives are enrichment
            ctx.logger.warning("Medicine recommendation unavailable: %s", exc)

        await ctx.set(MemoryKeys.MEDICINES, {
            "names": names,
            "medicines": detected,
            "recommendations": recommendations,
        })

        confidence = recommendations.get("overall_confidence")
        confidence = (confidence / 100.0) if isinstance(confidence, (int, float)) else None
        return AgentOutcome(
            summary=f"Resolved {len(names)} medicine(s) and found alternatives/generics.",
            confidence=confidence,
            details={"medicines": names},
        )
