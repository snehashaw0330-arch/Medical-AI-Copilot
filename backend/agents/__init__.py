"""Multi-Agent AI Medical Copilot.

An event-driven, provider-agnostic agent layer that orchestrates the project's
existing capabilities (OCR, medicine matching, disease prediction, drug
interactions, RAG, clinical decision support, reports) as specialised,
collaborating agents — without changing or removing any existing feature.

Public surface (imported lazily to avoid pulling heavy deps at import time):

* ``router``       — FastAPI router mounted at ``/agents``
* ``get_manager``  — the process-wide :class:`AgentManager`

Architecture (see the sibling modules):

* ``base_agent`` / ``implementations/`` — the nine specialised agents
* ``agent_registry`` / ``task_router`` / ``workflow_engine`` — orchestration
* ``context_manager`` / ``memory`` / ``event_bus`` — shared context + messaging
* ``run_store`` / ``logger`` — observability
* ``config/`` + ``backend/llm/`` — configuration + provider-agnostic LLM
"""

from __future__ import annotations

from typing import Any

__all__ = ["router", "get_manager"]


def __getattr__(name: str) -> Any:  # lazy exports (avoid import cycles / heavy deps)
    if name == "router":
        from backend.agents.router import router

        return router
    if name == "get_manager":
        from backend.agents.agent_manager import get_manager

        return get_manager
    raise AttributeError(name)
