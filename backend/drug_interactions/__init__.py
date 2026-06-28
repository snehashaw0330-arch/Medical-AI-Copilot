"""Drug Interaction Analysis module.

Production-ready, source-agnostic drug–drug interaction + per-drug warning
analysis for the Medical AI Assistant. Public surface:

* :data:`router`           — FastAPI router (mounted at ``/interactions``)
* :func:`analyze_medicines` — coroutine used by the OCR pipeline for auto-analysis
* :func:`get_service`       — the process-wide :class:`DrugInteractionService`

See ``service.py`` for the pluggable data-source architecture (JSON / CSV /
SQLite today; OpenFDA / RxNorm / DrugBank ready to plug in).
"""

from backend.drug_interactions.router import router
from backend.drug_interactions.service import analyze_medicines, get_service

__all__ = ["router", "analyze_medicines", "get_service"]
