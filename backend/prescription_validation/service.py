"""Async orchestration + persistence for Prescription Validation.

The validation *logic* is pure and synchronous (see :mod:`validator`); this
layer only:

* runs it (off the event loop is unnecessary — the checks are microseconds — so
  it is called directly), and
* persists each result to a history store using the same async-SQLAlchemy
  contract as the OCR-history / interaction / clinical modules.

Design contract (identical to the other modules):

* **Best-effort persistence.** Saving to history never raises, so a DB problem
  can never break a validation response or the OCR flow that triggered it.
* **Async, cross-DB store.** SQLite by default; point ``VALIDATION_DB_URL`` (or
  the shared ``DATABASE_URL``) at PostgreSQL for production with no code changes.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings
from backend.prescription_validation import rules, validator
from backend.prescription_validation.models import Base, ValidationRecord, utcnow
from backend.prescription_validation.schemas import (
    MedicineInput,
    ValidationReport,
    ValidationRequest,
)

logger = logging.getLogger("prescription_validation")


# ==========================================================================
# Persistence (async; same contract as the other history stores)
# ==========================================================================
_engine = create_async_engine(
    settings.VALIDATION_DB_URL, echo=False, pool_pre_ping=True, future=True
)
_Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False, class_=AsyncSession
)
_db_init_lock = asyncio.Lock()
_db_ready = False


async def _ensure_db() -> None:
    """Create the history table on first use (idempotent, race-safe)."""
    global _db_ready
    if _db_ready:
        return
    async with _db_init_lock:
        if _db_ready:
            return
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_ready = True
        logger.info(
            "Prescription-validation history store ready (%s)",
            settings.VALIDATION_DB_URL.split("://")[0],
        )


# ==========================================================================
# Service
# ==========================================================================
class PrescriptionValidationService:
    """Runs the validator and manages the validation history store."""

    async def validate(self, req: ValidationRequest) -> ValidationReport:
        """Validate one prescription and (optionally) persist the result."""
        report = validator.validate(
            req.medicines,
            raw_text=req.raw_text,
            fields=req.fields,
            low_confidence=settings.VALIDATION_LOW_CONFIDENCE,
        )
        if req.persist:
            report.id = await self._save(report, req)
        return report

    # -- persistence -------------------------------------------------------
    async def _save(
        self, report: ValidationReport, req: ValidationRequest
    ) -> str | None:
        """Persist one validation. Best-effort: never raises."""
        try:
            await _ensure_db()
            record_id = uuid.uuid4().hex
            report.id = record_id
            report.created_at = utcnow()

            names = [
                (m.name or m.raw_text or "").strip().lower()
                for m in req.medicines
                if (m.name or m.raw_text)
            ]
            row = ValidationRecord(
                id=record_id,
                created_at=report.created_at,
                source_record_id=req.source_record_id,
                medicine_names=",".join(n for n in names if n),
                medicine_count=report.medicine_count,
                validation_score=report.validation_score,
                risk_level=report.risk_level.value,
                issue_count=len(report.issues),
                summary=report.summary,
                report=report.model_dump(mode="json"),
            )
            async with _Session() as session:
                session.add(row)
                await session.commit()
            logger.info(
                "Saved prescription validation %s (risk=%s, score=%.1f, %d issue(s))",
                record_id, report.risk_level.value, report.validation_score,
                len(report.issues),
            )
            return record_id
        except Exception:  # noqa: BLE001 — persistence must never break validation
            logger.exception("Failed to save prescription validation")
            return None

    # -- history reads -----------------------------------------------------
    async def list_history(self, *, page: int = 1, page_size: int = 10) -> dict:
        """Return a paginated page of past validations (newest first)."""
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with _Session() as session:
            total = await session.scalar(select(func.count(ValidationRecord.id))) or 0
            stmt = (
                select(ValidationRecord)
                .order_by(ValidationRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return {
            "items": [r.item() for r in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "pages": (int(total) + page_size - 1) // page_size,
        }

    async def get_history(self, record_id: str) -> dict | None:
        """Return the full stored report for one validation, or None if missing."""
        await _ensure_db()
        async with _Session() as session:
            row = await session.get(ValidationRecord, record_id)
            return row.report if row else None

    async def clear_history(self) -> int:
        """Delete every stored validation. Returns the number removed."""
        await _ensure_db()
        async with _Session() as session:
            count = await session.scalar(select(func.count(ValidationRecord.id))) or 0
            await session.execute(delete(ValidationRecord))
            await session.commit()
        logger.info("Cleared prescription-validation history (%d records)", count)
        return int(count)


# Process-wide singleton.
_SERVICE: PrescriptionValidationService | None = None


def get_service() -> PrescriptionValidationService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PrescriptionValidationService()
    return _SERVICE


# ==========================================================================
# Convenience coroutines used by the OCR pipeline for auto-validation.
# ==========================================================================
async def validate_prescription(req: ValidationRequest) -> ValidationReport:
    """Module-level shortcut around :meth:`PrescriptionValidationService.validate`."""
    return await get_service().validate(req)


def _medicines_from_ocr(ocr_result: dict) -> list[MedicineInput]:
    """Map an OCR result's ``medicines`` list onto :class:`MedicineInput`."""
    out: list[MedicineInput] = []
    for m in ocr_result.get("medicines", []) or []:
        out.append(MedicineInput(
            raw_text=m.get("raw_text", "") or "",
            name=m.get("name"),
            dosage=m.get("dosage"),
            frequency=m.get("frequency"),
            frequency_expanded=m.get("frequency_expanded"),
            duration=m.get("duration"),
            instructions=m.get("instructions"),
            confidence=float(m.get("confidence", 1.0) or 0.0),
            needs_review=bool(m.get("needs_review", False)),
            candidates=m.get("candidates", []) or [],
            details=m.get("details"),
        ))
    return out


async def validate_from_ocr(
    ocr_result: dict,
    *,
    persist: bool = True,
    source_record_id: str | None = None,
) -> ValidationReport:
    """Build a request from an OCR result dict and validate it.

    Used by the OCR pipeline for automatic post-OCR validation (Requirement 8).
    """
    req = ValidationRequest(
        medicines=_medicines_from_ocr(ocr_result),
        raw_text=ocr_result.get("raw_text", "") or "",
        fields=ocr_result.get("fields"),
        overall_confidence=ocr_result.get("overall_confidence"),
        persist=persist,
        source_record_id=source_record_id,
    )
    return await get_service().validate(req)


__all__ = [
    "PrescriptionValidationService",
    "get_service",
    "validate_prescription",
    "validate_from_ocr",
]
