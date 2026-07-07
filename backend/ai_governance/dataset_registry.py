"""Dataset registry — a governed record of every dataset in the platform.

Tracks each dataset's version, source, size, date added and purpose. On first use
it **seeds** the registry with the datasets this project actually uses (the
medicine dataset, drug-interaction knowledge, symptom→disease training data, the
handwritten-prescription evaluation set and the RAG knowledge base), reading the
real medicine CSV size from disk when available so the numbers are truthful.

Dependency-injected with the shared session factory; unit-testable in isolation.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.ai_governance.models import DatasetRecord, utcnow
from backend.ai_governance.schemas import DatasetEntry, DatasetRegisterRequest
from backend.ai_governance.version_manager import VersionManager
from backend.config import settings

logger = logging.getLogger("ai_governance")


def _medicine_dataset_size() -> str:
    """Best-effort human-readable size of the shipped medicine dataset."""
    try:
        path = Path(settings.MEDICINE_CSV)
        if not path.exists():
            return "unknown"
        # Row count is cheap and more meaningful than bytes for a CSV.
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            rows = sum(1 for _ in fh) - 1
        mb = path.stat().st_size / (1024 * 1024)
        return f"{max(rows, 0):,} rows ({mb:.1f} MB)"
    except Exception:  # noqa: BLE001
        return "unknown"


class DatasetRegistry:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession],
                 versions: VersionManager) -> None:
        self._Session = session_factory
        self._versions = versions

    def _seed_defaults(self) -> list[dict]:
        v = self._versions.current()
        return [
            {"name": "Medicine Dataset", "version": v.dataset_version,
             "source": "Curated pharmaceutical catalogue (CSV)",
             "size": _medicine_dataset_size(), "date_added": "2024-11-01",
             "purpose": "Medicine matching, drug information and recommendations."},
            {"name": "Drug Interactions", "version": "drug-interactions-2024.10",
             "source": "Public DDI knowledge (JSON/CSV)", "size": "curated",
             "date_added": "2024-10-20",
             "purpose": "Drug–drug interaction detection and severity grading."},
            {"name": "Symptom→Disease", "version": "symptom-disease-2024.10",
             "source": "Open symptom-checker training data", "size": "training corpus",
             "date_added": "2024-10-10",
             "purpose": "Disease prediction from symptoms and clinical context."},
            {"name": "Handwritten Prescriptions", "version": "handwritten-prescriptions-2024.09",
             "source": "Illegible/handwritten prescription image set", "size": "image dataset",
             "date_added": "2024-09-15",
             "purpose": "OCR evaluation and accuracy benchmarking."},
            {"name": "Medical Knowledge Base", "version": v.rag_index_version,
             "source": "Clinical reference documents", "size": "vector-indexed corpus",
             "date_added": "2024-11-06",
             "purpose": "Retrieval-augmented grounding of recommendations (RAG)."},
        ]

    async def ensure_seeded(self) -> None:
        async with self._Session() as session:
            existing = (await session.execute(select(DatasetRecord.key))).scalars().first()
            if existing is not None:
                return
            for d in self._seed_defaults():
                session.add(DatasetRecord(key=f"{d['name']}@{d['version']}", **d))
            await session.commit()
            logger.info("Seeded dataset registry with %d datasets", len(self._seed_defaults()))

    async def list_datasets(self) -> list[DatasetEntry]:
        await self.ensure_seeded()
        async with self._Session() as session:
            rows = (await session.execute(
                select(DatasetRecord).order_by(DatasetRecord.name, DatasetRecord.version)
            )).scalars().all()
        return [DatasetEntry(**r.item()) for r in rows]

    async def register(self, req: DatasetRegisterRequest) -> DatasetEntry:
        key = f"{req.name}@{req.version}"
        async with self._Session() as session:
            row = await session.get(DatasetRecord, key)
            if row is None:
                row = DatasetRecord(key=key, name=req.name, version=req.version)
                session.add(row)
            row.source = req.source
            row.size = req.size
            row.date_added = req.date_added
            row.purpose = req.purpose
            row.updated_at = utcnow()
            await session.commit()
            return DatasetEntry(**row.item())
