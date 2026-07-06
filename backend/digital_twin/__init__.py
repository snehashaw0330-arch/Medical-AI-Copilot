"""Digital Twin module.

A continuously-evolving virtual health profile per patient. It aggregates every
prior analysis the platform already stores (OCR, disease prediction, medicines,
drug interactions, clinical decisions and generated reports) into one intelligent
model — a health score, trend analysis, future-risk prediction, a timeline and
RAG-enriched recommendations — without changing or removing any existing feature.

Public surface:

* :data:`router`      — FastAPI router (mounted at ``/digital-twin``)
* :func:`get_service` — the process-wide :class:`DigitalTwinService`

Internal layers (see the individual modules):

* ``health_score``      — the 0..100 score + six-factor breakdown (pure)
* ``trend_engine``      — improving/stable/worsening classification (pure)
* ``risk_engine``       — future-risk prediction (pure)
* ``prediction_engine`` — short-horizon forecast (pure)
* ``timeline_engine``   — chronological health journey (pure)
* ``service``           — aggregation across stores + RAG + persistence (async)
"""

from backend.digital_twin.router import router
from backend.digital_twin.service import get_service

__all__ = ["router", "get_service"]
