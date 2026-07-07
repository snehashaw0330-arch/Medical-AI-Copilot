"""AI Governance, Audit, Explainability & Reproducibility module.

Turns the Medical AI Assistant into an enterprise-grade platform where every AI
decision is **explainable, traceable, auditable, reproducible and versioned**.

Public surface
--------------
* ``router``            — the FastAPI router (mounted at ``/governance``).
* ``get_service``       — the singleton composition root (DI orchestrator).
* ``AuditMiddleware``   — ASGI middleware that audits every API request.
* ``record_trace_from_ocr`` — best-effort hook the OCR pipeline calls to capture
  a live decision trace (never raises, never blocks the OCR response).

The module is strictly **additive**: it reads the existing report store read-only,
owns its own database, and does not alter any existing route or behaviour.
"""

from __future__ import annotations

import logging

from backend.ai_governance.audit_logger import AuditMiddleware
from backend.ai_governance.router import router
from backend.ai_governance.service import get_service

logger = logging.getLogger("ai_governance")

__all__ = ["router", "get_service", "AuditMiddleware", "record_trace_from_ocr"]


async def record_trace_from_ocr(
    ocr_result: dict, *, processing_time: float = 0.0,
    source_report_id: str | None = None,
) -> str | None:
    """Capture a live AI decision trace from an OCR analysis result.

    Best-effort and non-fatal by contract: any failure is logged and swallowed so
    the OCR response is never blocked or broken. Returns the new trace id (or
    ``None`` on failure).
    """
    try:
        trace = await get_service().tracker.record_from_ocr(
            ocr_result, processing_time=processing_time,
            source_report_id=source_report_id,
        )
        return trace.trace_id
    except Exception:  # noqa: BLE001 — governance must never break OCR
        logger.exception("Governance trace capture failed (OCR unaffected)")
        return None
