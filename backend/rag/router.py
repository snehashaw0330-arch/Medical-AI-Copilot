"""FastAPI routes for the RAG subsystem (all async).

Endpoints
---------
* ``GET  /rag/status``        — readiness + index stats
* ``POST /rag/index``         — (re)build the vector index from documents/
* ``POST /rag/query``         — answer a free-text question with citations
* ``POST /rag/medicine-info`` — structured drug profiles + interactions
* ``POST /rag/upload``        — upload a txt/pdf/md doc (optionally re-index)
* ``POST /rag/prescription``  — OCR an image → extract medicines → retrieve info

The router never lets a RAG failure crash the app: dependency/configuration
problems surface as actionable 4xx/5xx responses with clear messages.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from backend.rag.config import config, get_logger
from backend.rag.rag_service import get_rag_service
from backend.rag.schemas import (
    IndexResponse,
    MedicineInfoRequest,
    MedicineInfoResponse,
    PrescriptionRAGResponse,
    QueryRequest,
    QueryResponse,
    StatusResponse,
    UploadResponse,
)

router = APIRouter(prefix="/rag", tags=["rag"])
logger = get_logger("rag.router")

_ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


@router.get("/status", response_model=StatusResponse)
async def rag_status() -> StatusResponse:
    """Report whether RAG is ready and how much is indexed."""
    return StatusResponse(**get_rag_service().status())


@router.post("/index", response_model=IndexResponse)
async def rag_index(
    reset: bool = Query(default=True, description="Drop the existing index before rebuilding."),
) -> IndexResponse:
    """Embed every document in the knowledge folder and (re)build the index."""
    try:
        result = await get_rag_service().aindex(reset=reset)
        return IndexResponse(**result)
    except RuntimeError as exc:
        # Missing embedding deps -> actionable 503.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Indexing failed")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}") from exc


@router.post("/query", response_model=QueryResponse)
async def rag_query(req: QueryRequest) -> QueryResponse:
    """Retrieve relevant context and generate a grounded answer."""
    try:
        result = await get_rag_service().aquery(req.question, top_k=req.top_k)
        return QueryResponse(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc


@router.post("/medicine-info", response_model=MedicineInfoResponse)
async def rag_medicine_info(req: MedicineInfoRequest) -> MedicineInfoResponse:
    """Structured profile (uses, dosage, side effects, …) + interaction check."""
    try:
        result = await get_rag_service().amedicine_info(req.medicines)
        return MedicineInfoResponse(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("medicine-info failed")
        raise HTTPException(status_code=500, detail=f"medicine-info failed: {exc}") from exc


@router.post("/upload", response_model=UploadResponse)
async def rag_upload(
    file: UploadFile = File(...),
    reindex: bool = Query(default=True, description="Rebuild the index after upload."),
) -> UploadResponse:
    """Add a knowledge document (txt / pdf / md) to the documents folder."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in config.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(config.SUPPORTED_EXTENSIONS)}",
        )

    dest = Path(config.DOCUMENTS_DIR) / Path(file.filename).name
    try:
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()
    logger.info("Knowledge document uploaded: %s", dest.name)

    index_result = None
    if reindex:
        try:
            index_result = IndexResponse(**await get_rag_service().aindex(reset=True))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return UploadResponse(
        filename=dest.name,
        saved=True,
        reindexed=reindex and index_result is not None,
        index=index_result,
    )


@router.post("/prescription", response_model=PrescriptionRAGResponse)
async def rag_prescription(
    file: UploadFile = File(...),
) -> PrescriptionRAGResponse:
    """End-to-end: OCR an image, extract medicines, retrieve their info.

    Implements the full assistant flow for "I uploaded this prescription":
    OCR (Step 1) → extract medicines (Step 2) → vector search (Step 3) →
    retrieve documents (Step 4) → generate answer (Step 5).
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_IMAGE:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type '{suffix}'. Allowed: {sorted(_ALLOWED_IMAGE)}",
        )

    # Reuse the existing OCR pipeline verbatim (no changes to it).
    from backend.config import settings as app_settings
    from backend.ocr.pipeline import run_pipeline

    dest = Path(app_settings.UPLOAD_DIR) / f"{uuid.uuid4().hex}{suffix}"
    try:
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    try:
        import asyncio

        ocr = await asyncio.to_thread(run_pipeline, str(dest))
        medicines = [m.name for m in ocr.medicines if m.name]
        info = await get_rag_service().amedicine_info(medicines) if medicines else {
            "medicines": [], "interactions": None, "provider": "offline",
        }
        return PrescriptionRAGResponse(
            extracted_medicines=medicines,
            ocr_provider=ocr.provider,
            ocr_confidence=ocr.overall_confidence,
            info=MedicineInfoResponse(**info),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("prescription RAG flow failed")
        raise HTTPException(status_code=500, detail=f"Prescription analysis failed: {exc}") from exc
    finally:
        dest.unlink(missing_ok=True)
