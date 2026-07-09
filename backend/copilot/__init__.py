"""AI Medical Copilot Workspace.

A session-scoped orchestrator that turns the Medical AI Assistant's individual
modules into one cooperating workspace. On every upload it automatically runs the
full clinical pipeline —

    receive → OCR → extract medicines → drug interactions → disease prediction →
    retrieve evidence (RAG) → clinical decision → AI summary → treatment
    suggestions → follow-up suggestions → final medical report

— while **remembering the current patient for the session**: each analysis folds
into an evolving patient context, and every action is recorded on an AI activity
timeline and a reasoning trace.

This module is purely additive: it only *reads* from the existing subsystems (OCR,
disease, drug interactions, RAG, clinical decision, report generator, LLM) and
changes none of them.

Public surface:

* :data:`router`      — FastAPI router (mounted at ``/copilot``)
* :func:`get_service` — the process-wide :class:`CopilotService`
"""

from backend.copilot.router import router
from backend.copilot.service import get_service

__all__ = ["router", "get_service"]
