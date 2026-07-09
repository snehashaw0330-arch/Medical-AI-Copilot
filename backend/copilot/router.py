"""FastAPI routes for the AI Medical Copilot Workspace (all async).

Endpoints
---------
* ``POST /copilot/analyze``  — run the full 11-stage workflow (multipart: optional
  prescription file + patient/medicine/symptom fields). Updates session context.
* ``POST /copilot/chat``     — ask the Copilot a question grounded in the session.
* ``GET  /copilot/context``  — the remembered patient context + conversation.
* ``GET  /copilot/history``  — the analyses run in a session.
* ``GET  /copilot/pipeline`` — the static 11-stage pipeline (for the UI animation).

Every route wraps the service so a failure surfaces as an actionable HTTP error
rather than crashing the app. The uploaded image is never retained on disk beyond
the request.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from backend.config import settings
from backend.copilot.reasoning import PIPELINE
from backend.copilot.schemas import (
    CopilotAnalysis,
    CopilotChatRequest,
    CopilotChatResponse,
    CopilotContextResponse,
    CopilotHistoryResponse,
)
from backend.copilot.service import get_service

logger = logging.getLogger("copilot")

router = APIRouter(prefix="/copilot", tags=["copilot"])

_ALLOWED = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


def _split(value: str | None) -> list[str]:
    """Parse a comma/newline-separated form field into a clean list."""
    if not value:
        return []
    return [p.strip() for p in value.replace("\n", ",").split(",") if p.strip()]


@router.post("/analyze", response_model=CopilotAnalysis)
async def analyze(
    file: UploadFile | None = File(default=None),
    session_id: str | None = Form(default=None),
    medicines: str | None = Form(default=None),
    symptoms: str | None = Form(default=None),
    text: str | None = Form(default=None),
    patient_name: str | None = Form(default=None),
    age: int | None = Form(default=None),
    gender: str | None = Form(default=None),
    diagnosis: str | None = Form(default=None),
    include_rag: bool = Form(default=True),
    use_cache: bool = Form(default=True),
) -> CopilotAnalysis:
    """Run the Copilot workflow. Accepts an optional prescription image plus
    manual fields; at least one input (file, medicines, symptoms or text) should
    be present for a useful result."""
    dest: Path | None = None
    try:
        if file is not None and file.filename:
            suffix = Path(file.filename).suffix.lower()
            if suffix not in _ALLOWED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(_ALLOWED)}",
                )
            dest = Path(settings.UPLOAD_DIR) / f"copilot_{uuid.uuid4().hex}{suffix}"
            with open(dest, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

        _sess, analysis = await get_service().analyze(
            session_id=session_id,
            image_path=str(dest) if dest else None,
            text=text or "",
            medicines=_split(medicines),
            symptoms=_split(symptoms),
            patient_name=patient_name,
            age=age,
            gender=gender,
            diagnosis=diagnosis,
            include_rag=include_rag,
            use_cache=use_cache,
        )
        return analysis
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Copilot analyze failed")
        raise HTTPException(status_code=500, detail=f"Copilot analysis failed: {exc}") from exc
    finally:
        if file is not None:
            await file.close()
        if dest is not None:
            dest.unlink(missing_ok=True)  # never retain medical images on disk


@router.post("/chat", response_model=CopilotChatResponse)
async def chat(req: CopilotChatRequest) -> CopilotChatResponse:
    """Answer a clinician question grounded in the current patient session."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty.")
    try:
        return await get_service().chat(req.session_id, req.message.strip())
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown session: {req.session_id}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Copilot chat failed")
        raise HTTPException(status_code=500, detail=f"Copilot chat failed: {exc}") from exc


@router.get("/pipeline")
async def pipeline() -> dict:
    """Static 11-stage pipeline definition (UI renders it before/while a run)."""
    return {
        "steps": [
            {"order": i + 1, "key": key, "name": name}
            for i, (key, name) in enumerate(PIPELINE)
        ]
    }


@router.get("/context", response_model=CopilotContextResponse)
async def get_context(session_id: str = Query(...)) -> CopilotContextResponse:
    """Return the remembered patient context + conversation for a session."""
    try:
        return await get_service().get_context(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Copilot get_context failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history", response_model=CopilotHistoryResponse)
async def get_history(session_id: str = Query(...)) -> CopilotHistoryResponse:
    """Return the analyses run in a session (newest first)."""
    try:
        return await get_service().get_history(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Copilot get_history failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
