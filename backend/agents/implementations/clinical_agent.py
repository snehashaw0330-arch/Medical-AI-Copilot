"""Clinical Decision Agent — synthesise all prior outputs into a decision.

Reads the medicines, disease hypotheses, interaction report and knowledge context
from shared memory and delegates to the existing Clinical Decision Support engine
to produce recommendations, warnings and a risk assessment. It reuses the
Drug-Interaction Agent's report (no recomputation) and disables the CDSS's own RAG
call (the Knowledge Agent already gathered evidence).
"""

from __future__ import annotations

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys


def _int_or_none(value) -> int | None:
    if value is None:
        return None
    import re

    m = re.search(r"\d{1,3}", str(value))
    return int(m.group()) if m else None


class ClinicalAgent(BaseAgent):
    name = ac.CLINICAL
    title = "Clinical Decision Agent"
    description = "Synthesise all prior outputs into recommendations, warnings and a risk assessment."
    reads = (MemoryKeys.MEDICINES, MemoryKeys.DISEASE, MemoryKeys.INTERACTIONS, MemoryKeys.KNOWLEDGE)
    writes = (MemoryKeys.CLINICAL,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        inputs = await ctx.get(MemoryKeys.INPUTS, {})
        medicines = await ctx.get(MemoryKeys.MEDICINES, {})
        disease = await ctx.get(MemoryKeys.DISEASE, {})
        interactions = await ctx.get(MemoryKeys.INTERACTIONS, {})
        ocr = await ctx.get(MemoryKeys.OCR, {})

        names = (medicines or {}).get("names", [])
        symptoms = (disease or {}).get("symptoms", []) or inputs.get("symptoms", []) or []
        if not names and not symptoms:
            return AgentOutcome.skipped("No medicines or symptoms to reason over.")

        # Patient context from inputs, falling back to OCR-parsed fields.
        fields = (ocr or {}).get("fields", {}) if ocr else {}
        age = _int_or_none(inputs.get("age") or fields.get("age"))
        gender = inputs.get("gender") or fields.get("gender")
        diagnosis = inputs.get("diagnosis") or fields.get("diagnosis")

        from backend.clinical_decision import analyze_clinical
        from backend.clinical_decision.schemas import ClinicalAnalysisRequest

        req = ClinicalAnalysisRequest(
            medicines=names, symptoms=symptoms, diagnosis=diagnosis,
            age=age, gender=gender,
            include_rag=False,            # Knowledge Agent owns RAG
            run_disease_prediction=False,  # Disease Agent already did this
            persist=False,
        )
        report = await analyze_clinical(req, interaction_report=interactions or None)
        data = report.model_dump(mode="json")

        risk_level = data.get("risk_level")
        summary = data.get("clinical_summary", "")
        await ctx.set(MemoryKeys.CLINICAL, {
            "risk_level": risk_level,
            "risk_score": data.get("risk_score"),
            "summary": summary,
            "red_flags": data.get("red_flags", []),
            "recommended_next_steps": data.get("recommended_next_steps", []),
            "contraindications": data.get("contraindications", []),
            "full": data,
        })
        confidence = data.get("confidence")
        confidence = (confidence / 100.0) if isinstance(confidence, (int, float)) else None
        return AgentOutcome(
            summary=f"Clinical assessment complete — risk level: {risk_level}.",
            confidence=confidence,
            details={"risk_level": risk_level, "red_flags": len(data.get("red_flags", []))},
        )
