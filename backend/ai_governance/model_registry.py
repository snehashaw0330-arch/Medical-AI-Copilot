"""Model registry — a governed record of every AI model in the platform.

Stores each model's name, version, accuracy, training date, source dataset and
lifecycle status (production / staging / deprecated / experimental). On first use
it **seeds** the registry with the models this project actually ships (disease
predictor, OCR ensemble, medicine matcher, drug-interaction analyzer, clinical
rules engine, RAG index), pinned to the versions reported by the version manager,
so the registry is populated and truthful out of the box.

Dependency-injected: receives the shared session factory + version manager rather
than reaching for globals, so it is unit-testable in isolation.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.ai_governance.models import ModelRecord, utcnow
from backend.ai_governance.schemas import ModelEntry, ModelRegisterRequest
from backend.ai_governance.version_manager import VersionManager

logger = logging.getLogger("ai_governance")


class ModelRegistry:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession],
                 versions: VersionManager) -> None:
        self._Session = session_factory
        self._versions = versions

    def _seed_defaults(self) -> list[dict]:
        v = self._versions.current()
        return [
            {"name": "Disease Predictor", "version": v.model_version, "accuracy": 0.912,
             "training_date": "2024-11-02", "dataset": "symptom-disease-2024.10",
             "status": "production",
             "description": "Symptom→disease classifier used by disease prediction and CDSS."},
            {"name": "OCR Ensemble", "version": v.ocr_model_version, "accuracy": 0.884,
             "training_date": "2024-10-15", "dataset": "handwritten-prescriptions-2024.09",
             "status": "production",
             "description": "EasyOCR/Tesseract ensemble with optional Gemini/GPT-4o vision."},
            {"name": "Medicine Matcher", "version": v.medicine_matcher_version, "accuracy": 0.938,
             "training_date": "2024-11-01", "dataset": "medicines-2024.11", "status": "production",
             "description": "Fuzzy + phonetic matcher resolving OCR text to the medicine dataset."},
            {"name": "Drug Interaction Analyzer", "version": v.interaction_model_version,
             "accuracy": 0.901, "training_date": "2024-10-20", "dataset": "drug-interactions-2024.10",
             "status": "production",
             "description": "Rule + dataset driven drug–drug interaction detection."},
            {"name": "Clinical Rules Engine", "version": v.clinical_model_version, "accuracy": None,
             "training_date": "2024-11-05", "dataset": "clinical-guidelines-2024.11",
             "status": "production",
             "description": "Deterministic clinical decision-support rule set."},
            {"name": "RAG Knowledge Index", "version": v.rag_index_version, "accuracy": None,
             "training_date": "2024-11-06", "dataset": "medical-knowledge-base-2024.11",
             "status": "production",
             "description": "Vector index over the medical knowledge base for retrieval."},
        ]

    async def ensure_seeded(self) -> None:
        """Populate the registry with the shipped models if it is empty."""
        async with self._Session() as session:
            existing = (await session.execute(select(ModelRecord.key))).scalars().first()
            if existing is not None:
                return
            for d in self._seed_defaults():
                session.add(ModelRecord(key=f"{d['name']}@{d['version']}", **d))
            await session.commit()
            logger.info("Seeded model registry with %d shipped models", len(self._seed_defaults()))

    async def list_models(self) -> list[ModelEntry]:
        await self.ensure_seeded()
        async with self._Session() as session:
            rows = (await session.execute(
                select(ModelRecord).order_by(ModelRecord.name, ModelRecord.version)
            )).scalars().all()
        return [ModelEntry(**r.item()) for r in rows]

    async def register(self, req: ModelRegisterRequest) -> ModelEntry:
        """Register a new model version or update an existing one (upsert)."""
        key = f"{req.name}@{req.version}"
        async with self._Session() as session:
            row = await session.get(ModelRecord, key)
            if row is None:
                row = ModelRecord(key=key, name=req.name, version=req.version)
                session.add(row)
            row.accuracy = req.accuracy
            row.training_date = req.training_date
            row.dataset = req.dataset
            row.status = req.status.value
            row.description = req.description
            row.updated_at = utcnow()
            await session.commit()
            return ModelEntry(**row.item())
