"""Disease Prediction Agent — likely conditions from symptoms, with alternatives.

Delegates to the existing scikit-learn disease-prediction service. Symptoms come
from the caller; if none were supplied the agent skips (predictions require
symptoms). Model inference is synchronous → run in a worker thread.
"""

from __future__ import annotations

import asyncio

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys
from backend.agents.security import sanitize_tokens


class DiseaseAgent(BaseAgent):
    name = ac.DISEASE
    title = "Disease Prediction Agent"
    description = "Predict likely conditions from symptoms with confidence and alternatives."
    reads = (MemoryKeys.INPUTS, MemoryKeys.OCR)
    writes = (MemoryKeys.DISEASE,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        inputs = await ctx.get(MemoryKeys.INPUTS, {})
        symptoms = sanitize_tokens(inputs.get("symptoms"), max_items=40)
        if not symptoms:
            return AgentOutcome.skipped("No symptoms supplied — disease prediction skipped.")

        from backend.disease.service import get_service

        svc = get_service()
        response = await asyncio.to_thread(svc.predict, symptoms, 5)
        predictions = [
            {"disease": p.disease, "confidence": p.confidence,
             "matched_symptoms": p.matched_symptoms, "explanation": p.explanation}
            for p in response.predictions
        ]
        await ctx.set(MemoryKeys.DISEASE, {
            "predictions": predictions,
            "confidence_level": response.confidence_level,
            "warnings": response.warnings,
            "symptoms": symptoms,
        })

        top = predictions[0] if predictions else None
        confidence = (top["confidence"] / 100.0) if top else None
        summary = (f"Top condition: {top['disease']} ({top['confidence']:.0f}%)."
                   if top else "No condition matched the symptoms.")
        return AgentOutcome(summary=summary, confidence=confidence,
                            details={"predictions": predictions[:3]})

    async def health_check(self) -> tuple[bool, str]:
        try:
            import asyncio

            from backend.disease.service import get_service

            svc = await asyncio.to_thread(get_service)
            return True, f"Disease model loaded ({len(svc.classes)} conditions)."
        except Exception as exc:  # noqa: BLE001
            return False, f"Disease model unavailable: {exc}"
