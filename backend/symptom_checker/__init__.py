"""Symptom Checker & Triage module.

Production-ready, deterministic symptom triage for the Medical AI Assistant. A
user enters or picks symptoms from a categorized catalog; this module resolves
them, runs the existing disease-prediction model, enriches the result with the
RAG knowledge base, and turns everything into an actionable, safety-first triage
assessment — possible conditions, a severity level, a four-level urgency grade,
red-flag symptoms with an emergency warning, a recommended specialist, tests and
home-care advice, plus evidence-based references.

Public surface:

* :data:`router`            — FastAPI router (mounted at ``/symptoms``)
* :func:`analyze_symptoms`  — coroutine around the service's ``analyze``
* :func:`get_service`       — the process-wide :class:`SymptomCheckerService`

Internal layers (see the individual modules):

* ``symptom_matcher`` — the categorized catalog + fuzzy symptom matching (pure)
* ``triage_engine``   — red flags, urgency, specialist, tests, home care (pure)
* ``service``         — async orchestration (disease model + RAG) + persistence
"""

from backend.symptom_checker.router import router
from backend.symptom_checker.service import analyze_symptoms, get_service

__all__ = ["router", "analyze_symptoms", "get_service"]
