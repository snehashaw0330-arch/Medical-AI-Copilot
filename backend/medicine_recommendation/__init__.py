"""Medicine Alternatives & Recommendation module.

Production-ready medicine information + alternatives engine for the Medical AI
Assistant. Given medicines detected by OCR (or typed), it resolves each against
the project's existing ~248k-row medicine dataset, retrieves structured drug
information, finds generic equivalents / substitute brands / same-class similar
medicines, enriches the harder fields (contraindications, pregnancy, food,
storage) from the RAG knowledge base, and produces an AI recommendation report
that explains *why* each alternative is suggested — with a confidence score.

Public surface:

* :data:`router`               — FastAPI router (mounted at ``/medicine``)
* :func:`recommend_medicines`  — coroutine for a :class:`MedicineRecommendRequest`
* :func:`recommend_from_ocr`   — coroutine the OCR flow uses for auto-recommend
* :func:`get_service`          — the process-wide recommendation service

Internal layers (see the individual modules):

* ``alternative_finder``      — dataset resolution + substitutes/similar (pure)
* ``recommendation_engine``   — drug-info card, reasons, summary, confidence (pure)
* ``service``                 — async orchestration (dataset + RAG) + persistence
"""

from backend.medicine_recommendation.router import router
from backend.medicine_recommendation.service import (
    get_service,
    recommend_from_ocr,
    recommend_medicines,
)

__all__ = ["router", "get_service", "recommend_from_ocr", "recommend_medicines"]
