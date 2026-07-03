"""Medical Report Generator module.

Assembles a durable, exportable snapshot of one complete analysis — OCR output,
detected medicines, disease prediction, drug-interaction and clinical-decision
reports, RAG context and provenance — and renders it on demand as PDF, JSON or
HTML.

Public surface:

* :data:`router`            — FastAPI router (mounted at ``/reports``)
* :func:`generate_from_ocr` — coroutine used by the OCR flow for auto-generation
* :func:`get_service`       — the process-wide :class:`ReportService`

Internal layers (see the individual modules):

* ``report_builder`` — pure mapping: OCR result → structured ``ReportContent``
* ``templates``      — self-contained HTML rendering (stdlib only)
* ``pdf_generator``  — server-side PDF rendering (reportlab, lazy-imported)
* ``service``        — async persistence, image retention and exports
"""

from backend.report_generator.router import router
from backend.report_generator.service import generate_from_ocr, get_service

__all__ = ["router", "generate_from_ocr", "get_service"]
