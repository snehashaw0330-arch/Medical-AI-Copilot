"""Clinical Decision Support (CDSS) module.

Production-ready clinical decision support for the Medical AI Assistant. It fuses
the project's existing subsystems — OCR-extracted medicines, disease prediction,
drug-interaction analysis and the RAG knowledge base — through a deterministic,
auditable rules engine into a single risk-graded clinical report.

Public surface:

* :data:`router`            — FastAPI router (mounted at ``/clinical``)
* :func:`analyze_clinical`  — coroutine used by the OCR flow for auto-analysis
* :func:`get_service`       — the process-wide :class:`ClinicalDecisionService`

Internal layers (see the individual modules):

* ``rules_engine``          — pure medical knowledge (red flags, cautions, labs)
* ``risk_analyzer``         — fuses signals into a 0..100 score + risk level
* ``recommendation_engine`` — composes next steps, follow-up and the summary
* ``service``               — async orchestration + persistence
"""

from backend.clinical_decision.router import router
from backend.clinical_decision.service import analyze_clinical, get_service

__all__ = ["router", "analyze_clinical", "get_service"]
