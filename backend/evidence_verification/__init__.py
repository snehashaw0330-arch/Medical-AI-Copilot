"""AI Hallucination Detection & Evidence Verification Engine.

Verifies any AI-generated response against the medical evidence retrieved from the
RAG knowledge base, estimating whether the response is well-supported or
potentially hallucinated. For every response it computes evidence coverage,
citation strength, a hallucination-risk category (very low → critical) and a
confidence score, and flags unsupported claims, contradictions and missing
references.

It is purely additive: it only *reads* from the RAG knowledge base and changes no
existing subsystem. Any module can call :func:`verify_response` to verify its own
generated text before showing it to the user.

Public surface:

* :data:`router`          — FastAPI router (mounted at ``/verification``)
* :func:`verify_response` — coroutine to verify an already-generated response
* :func:`get_service`     — the process-wide :class:`VerificationService`
"""

from backend.evidence_verification.router import router
from backend.evidence_verification.service import get_service, verify_response

__all__ = ["router", "verify_response", "get_service"]
