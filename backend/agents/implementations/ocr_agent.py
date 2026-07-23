"""OCR Agent — image preprocessing, quality analysis and OCR into structured JSON.

Delegates to the existing OCR pipeline (`backend.ocr.pipeline.run_pipeline`) and
image-quality analyser, so no OCR logic is duplicated or changed. Runs the
CPU/IO-bound pipeline in a worker thread to keep the event loop free.
"""

from __future__ import annotations

import asyncio

from backend.agents.base_agent import AgentOutcome, BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.context_manager import AgentContext, MemoryKeys


class OCRAgent(BaseAgent):
    name = ac.OCR
    title = "OCR Agent"
    description = "Preprocess the prescription image, assess quality and run OCR into structured JSON."
    reads = (MemoryKeys.INPUTS,)
    writes = (MemoryKeys.OCR,)

    async def process(self, ctx: AgentContext) -> AgentOutcome:
        inputs = await ctx.get(MemoryKeys.INPUTS, {})
        image_path = inputs.get("image_path")
        if not image_path:
            return AgentOutcome.skipped("No prescription image supplied — OCR skipped.")

        # Image quality analysis (best-effort — never blocks OCR).
        quality: dict = {}
        try:
            from backend.ocr.image_quality import assess_image_quality

            report = await asyncio.to_thread(assess_image_quality, image_path)
            quality = {
                "overall_score": getattr(report, "overall_score", None),
                "rating": getattr(report, "rating", None),
                "passed": getattr(report, "passed", None),
            }
        except Exception as exc:  # noqa: BLE001
            ctx.logger.warning("Image quality analysis skipped: %s", exc)

        # OCR pipeline (heavy, sync) → run off the event loop.
        from backend.ocr.pipeline import run_pipeline

        result = await asyncio.to_thread(
            run_pipeline, image_path, inputs.get("provider")
        )
        ocr_dict = result.model_dump(mode="json")
        ocr_dict["quality"] = quality
        await ctx.set(MemoryKeys.OCR, ocr_dict)

        med_count = len(ocr_dict.get("medicines", []) or [])
        confidence = float(ocr_dict.get("overall_confidence") or 0.0)
        return AgentOutcome(
            summary=f"OCR extracted {med_count} medicine(s) via {ocr_dict.get('provider')}.",
            confidence=confidence,
            details={"medicine_count": med_count, "provider": ocr_dict.get("provider"),
                     "quality": quality},
        )

    async def health_check(self) -> tuple[bool, str]:
        try:
            import backend.ocr.pipeline  # noqa: F401 — import proves the OCR stack loads

            from backend.config import settings
            return True, f"OCR stack loaded (provider={settings.OCR_PROVIDER})."
        except Exception as exc:  # noqa: BLE001
            return False, f"OCR stack failed to load: {exc}"
