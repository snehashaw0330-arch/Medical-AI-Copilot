"""Clinical Reasoning Platform.

An enterprise, step-by-step AI clinical-reasoning layer that chains every existing
subsystem of the Medical AI Assistant — OCR, medicine detection/validation, drug
interactions, disease prediction, the RAG knowledge base and a deterministic
clinical-rules engine — and, instead of returning an answer directly, *shows its
work*: an ordered, animatable reasoning chain, a weighted confidence breakdown, a
differential with explicit rejection reasons, and a full Clinical Reasoning
Report.

This module is purely additive: it only reads from the other subsystems and never
changes their behaviour.

Public surface:

* :data:`router`       — FastAPI router (mounted at ``/reasoning``)
* :func:`reason`       — coroutine to run the pipeline (used by other flows)
* :func:`get_service`  — the process-wide :class:`ClinicalReasoningService`
"""

from backend.clinical_reasoning.router import router
from backend.clinical_reasoning.service import get_service, reason

__all__ = ["router", "reason", "get_service"]
