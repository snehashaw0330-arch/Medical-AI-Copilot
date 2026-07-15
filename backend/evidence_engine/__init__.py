"""Evidence-Based Medical Response Engine.

Grounds every AI-generated medical response in retrieved evidence from the
RAG knowledge base: retrieve -> rerank -> cite -> generate -> respond, with a
confidence score and full source attribution.

Public surface:

* :data:`router` — FastAPI routes under ``/evidence``.
* :func:`get_service` — the orchestration service (query/chat/history).
"""

from backend.evidence_engine.router import router
from backend.evidence_engine.service import get_service

__all__ = ["router", "get_service"]
