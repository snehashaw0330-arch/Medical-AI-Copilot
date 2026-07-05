"""Report Agent — generate the durable clinical report (PDF / JSON / HTML).

Delegates to the existing Medical Report Generator. It assembles an OCR-result-
shaped payload from shared memory (real OCR output when available, otherwise a
synthesised one from the resolved medicines) and attaches the interaction and
clinical sub-reports so the generated document reflects the full pipeline.
"""

from __future__ import annotations

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys


class ReportAgent(BaseAgent):
    name = ac.REPORT
    title = "Report Agent"
    description = "Generate the durable clinical report (PDF / JSON / HTML) from the assembled findings."
    reads = (MemoryKeys.OCR, MemoryKeys.CLINICAL, MemoryKeys.INTERACTIONS)
    writes = (MemoryKeys.REPORT,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        inputs = await ctx.get(MemoryKeys.INPUTS, {})
        ocr = await ctx.get(MemoryKeys.OCR, {})
        medicines = await ctx.get(MemoryKeys.MEDICINES, {}) or {}
        interactions = await ctx.get(MemoryKeys.INTERACTIONS, {})
        clinical = await ctx.get(MemoryKeys.CLINICAL, {})

        # Build the OCR-result-shaped payload the report generator expects.
        if ocr and ocr.get("medicines"):
            payload = dict(ocr)
        else:
            detected = medicines.get("medicines", [])
            if not detected:
                return AgentOutcome.skipped("Nothing to report (no medicines).")
            payload = {
                "provider": "multi-agent-pipeline",
                "medicines": [{
                    "raw_text": m.get("name", ""), "name": m.get("name"),
                    "dosage": m.get("dosage"), "frequency": m.get("frequency"),
                    "frequency_expanded": m.get("frequency"), "duration": m.get("duration"),
                    "instructions": None, "confidence": m.get("confidence") or 0.8,
                    "needs_review": False, "candidates": [], "details": None,
                } for m in detected],
                "fields": {}, "doctor_notes": [], "raw_text": inputs.get("text", "") or "",
                "overall_confidence": 0.8, "warnings": [],
            }

        # Attach the sub-reports so the document reflects the whole pipeline.
        if interactions:
            payload["drug_interactions"] = interactions
        if clinical and clinical.get("full"):
            payload["clinical_report"] = clinical["full"]

        try:
            from backend.report_generator import generate_from_ocr

            report_id = await generate_from_ocr(
                payload,
                filename=inputs.get("filename"),
                processing_time=ctx.elapsed_ms() / 1000.0,
                image_src=inputs.get("image_path"),
            )
        except Exception as exc:  # noqa: BLE001
            ctx.logger.warning("Report generation failed: %s", exc)
            return AgentOutcome.skipped(f"Report generation unavailable: {exc}")

        await ctx.set(MemoryKeys.REPORT, {
            "report_id": report_id,
            "formats": ["pdf", "json", "html"],
        })
        return AgentOutcome(
            summary=f"Clinical report generated (id: {report_id}).",
            confidence=1.0 if report_id else None,
            details={"report_id": report_id},
        )
