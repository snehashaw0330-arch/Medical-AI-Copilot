"""Medical Document Intelligence module — multi-document-type analysis.

Generalizes intake beyond prescriptions to Blood Test / CBC / LFT / KFT /
Lipid Profile / Thyroid reports, Discharge Summaries and Medical
Certificates: detect type -> extract text -> parse structured data -> RAG ->
clinical summary -> highlight abnormal findings -> AI explanation.

Public surface:
* ``router``           — FastAPI APIRouter mounted at ``/documents``.
* ``service``           — async persistence + orchestration (CRUD, stats).
* ``analyze_document``  — convenience hook for running the workflow directly.
"""

from backend.document_intelligence import service
from backend.document_intelligence.router import router
from backend.document_intelligence.service import analyze_document

__all__ = ["router", "service", "analyze_document"]
