"""Business logic for Drug Interaction Analysis.

Responsibilities, top to bottom:

1. **Dataset loading** — a small, source-agnostic abstraction (``InteractionDataSource``)
   so the knowledge base can be backed by JSON, CSV, SQLite *or* a future live
   API (OpenFDA / RxNorm / DrugBank) with no change to the analysis code.
2. **Name resolution** — map free-text / OCR'd medicine names onto known drugs
   using alias tables and fuzzy matching (no fabricated interactions).
3. **Analysis** — pairwise drug–drug interactions + per-drug warnings
   (food, alcohol, pregnancy, breastfeeding, kidney, liver, age, contraindications).
4. **RAG enrichment** — optional extra context from the existing knowledge base.
5. **Persistence** — async history store (SQLite now, PostgreSQL later).

Everything that performs I/O is async; CPU-bound dataset parsing runs in a
worker thread so the event loop is never blocked. Every public entry point logs
and degrades gracefully — a knowledge-base problem yields an informative report,
never a 500 that breaks OCR or the app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings
from backend.drug_interactions.models import Base, InteractionRecord, utcnow
from backend.drug_interactions.schemas import (
    DrugDrugInteraction,
    InteractionReport,
    MedicineWarnings,
    Severity,
)
from backend.drug_interactions.utils import (
    build_summary,
    coerce_severity,
    collect_recommendations,
    max_severity,
    normalize_name,
    severity_counts,
)

logger = logging.getLogger("drug_interactions")

# Optional fuzzy matcher (already a project dependency). Degrade to exact-only
# matching if it is somehow unavailable.
try:  # pragma: no cover - import guard
    from rapidfuzz import fuzz, process

    _HAS_FUZZY = True
except Exception:  # noqa: BLE001
    _HAS_FUZZY = False


# ==========================================================================
# Internal knowledge representation (what every data source produces)
# ==========================================================================
@dataclass
class InteractionKnowledge:
    """Normalised, in-memory view of the interaction knowledge base."""

    # "norm_a||norm_b" (sorted) -> raw interaction dict
    pairs: dict[str, dict] = field(default_factory=dict)
    # canonical drug name -> warning profile dict
    profiles: dict[str, dict] = field(default_factory=dict)
    # normalised alias/name -> canonical drug name
    alias_to_canonical: dict[str, str] = field(default_factory=dict)
    # normalised canonical names, for fuzzy matching
    match_keys: list[str] = field(default_factory=list)

    @staticmethod
    def pair_key(norm_a: str, norm_b: str) -> str:
        return "||".join(sorted((norm_a, norm_b)))


def _build_knowledge(
    interactions: list[dict], profiles: dict[str, dict]
) -> InteractionKnowledge:
    """Assemble an :class:`InteractionKnowledge` from raw records.

    This is the single convergence point for *every* data source — JSON, CSV and
    SQLite all reduce to ``(interactions, profiles)`` and call this builder, so
    matching/analysis behaviour is identical regardless of backend.
    """
    knowledge = InteractionKnowledge()

    # Profiles + alias map.
    for canonical, profile in profiles.items():
        canonical = str(canonical).strip()
        if not canonical:
            continue
        knowledge.profiles[canonical] = profile
        norm = normalize_name(canonical)
        knowledge.alias_to_canonical[norm] = canonical
        for alias in profile.get("aliases", []) or []:
            knowledge.alias_to_canonical[normalize_name(alias)] = canonical

    knowledge.match_keys = sorted(knowledge.alias_to_canonical.keys())

    # Pairwise interactions, keyed by the normalised drug names.
    for record in interactions:
        drugs = [d for d in (record.get("drugs") or []) if d]
        if len(drugs) < 2:
            continue
        # Store an entry for every drug pair the record covers (usually one).
        for a, b in combinations(drugs, 2):
            key = InteractionKnowledge.pair_key(normalize_name(a), normalize_name(b))
            knowledge.pairs[key] = record

    logger.info(
        "Loaded interaction knowledge: %d profiles, %d pairwise interactions",
        len(knowledge.profiles),
        len(knowledge.pairs),
    )
    return knowledge


# ==========================================================================
# Data sources (CSV / JSON / SQLite / API) — pluggable architecture
# ==========================================================================
class InteractionDataSource(ABC):
    """Abstract knowledge backend.

    Implementations only need to produce ``(interactions, profiles)`` in the
    canonical shape; :func:`_build_knowledge` does the rest. Add a new backend
    (e.g. live OpenFDA) by subclassing this and registering it in
    :func:`build_source` — no analysis code changes.
    """

    @abstractmethod
    def load(self) -> InteractionKnowledge:
        """Load and normalise the knowledge base (sync; run off the event loop)."""


class JSONDataSource(InteractionDataSource):
    """Loads the bundled ``interactions.json`` (default backend)."""

    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> InteractionKnowledge:
        data = json.loads(Path(self.path).read_text(encoding="utf-8"))
        return _build_knowledge(
            data.get("interactions", []) or [],
            data.get("profiles", {}) or {},
        )


class CSVDataSource(InteractionDataSource):
    """Loads interactions from a CSV (and optional ``*_profiles.csv`` sibling).

    Interactions CSV columns:
        drug_a, drug_b, severity, clinical_risk, explanation,
        recommendation, clinical_notes
    Profiles CSV columns (optional companion file):
        drug, aliases, contraindications, food, alcohol, pregnancy,
        breastfeeding, kidney, liver, age_restrictions
    List-valued profile cells are split on ``;``.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> InteractionKnowledge:
        import csv

        interactions: list[dict] = []
        with open(self.path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                interactions.append(
                    {
                        "drugs": [row.get("drug_a", ""), row.get("drug_b", "")],
                        "severity": row.get("severity", "none"),
                        "clinical_risk": row.get("clinical_risk", ""),
                        "explanation": row.get("explanation", ""),
                        "recommendation": row.get("recommendation", ""),
                        "clinical_notes": row.get("clinical_notes", ""),
                    }
                )

        profiles: dict[str, dict] = {}
        prof_path = Path(self.path).with_name(Path(self.path).stem + "_profiles.csv")
        if prof_path.exists():
            list_cols = (
                "aliases", "contraindications", "food", "alcohol", "pregnancy",
                "breastfeeding", "kidney", "liver", "age_restrictions",
            )
            with open(prof_path, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    drug = (row.get("drug") or "").strip()
                    if not drug:
                        continue
                    profiles[drug] = {
                        col: [s.strip() for s in (row.get(col) or "").split(";") if s.strip()]
                        for col in list_cols
                    }

        return _build_knowledge(interactions, profiles)


class SQLiteDataSource(InteractionDataSource):
    """Loads interactions from a SQLite database file.

    Expected schema (created by an ETL job, not by this app):
        interactions(drug_a, drug_b, severity, clinical_risk, explanation,
                     recommendation, clinical_notes)
        profiles(drug, aliases, contraindications, food, alcohol, pregnancy,
                 breastfeeding, kidney, liver, age_restrictions)
    List columns store ``;``-separated values.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> InteractionKnowledge:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            interactions = [
                {
                    "drugs": [r["drug_a"], r["drug_b"]],
                    "severity": r["severity"],
                    "clinical_risk": r["clinical_risk"],
                    "explanation": r["explanation"],
                    "recommendation": r["recommendation"],
                    "clinical_notes": r["clinical_notes"],
                }
                for r in conn.execute("SELECT * FROM interactions")
            ]
            profiles: dict[str, dict] = {}
            list_cols = (
                "aliases", "contraindications", "food", "alcohol", "pregnancy",
                "breastfeeding", "kidney", "liver", "age_restrictions",
            )
            try:
                for r in conn.execute("SELECT * FROM profiles"):
                    profiles[r["drug"]] = {
                        col: [s.strip() for s in (r[col] or "").split(";") if s.strip()]
                        for col in list_cols
                    }
            except sqlite3.OperationalError:
                logger.info("SQLite source has no 'profiles' table — interactions only")
            return _build_knowledge(interactions, profiles)
        finally:
            conn.close()


class RemoteAPIDataSource(InteractionDataSource):
    """Placeholder for live interaction APIs (OpenFDA / RxNorm / DrugBank).

    Intentionally not implemented yet — it documents the extension point. A real
    implementation would either (a) bulk-sync the API into the canonical shape
    here, or (b) override per-query lookups in the service. Until then, selecting
    this source raises a clear, actionable error rather than failing silently.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def load(self) -> InteractionKnowledge:
        raise NotImplementedError(
            f"The '{self.provider}' interaction source is not implemented yet. "
            "Set INTERACTIONS_SOURCE=auto (or point INTERACTIONS_DATASET at a "
            "json/csv/sqlite file) to use the bundled knowledge base. See "
            "RemoteAPIDataSource for the integration contract."
        )


def build_source() -> InteractionDataSource:
    """Choose a data source from settings (explicit override or path extension)."""
    explicit = (settings.INTERACTIONS_SOURCE or "auto").lower()
    path = settings.INTERACTIONS_DATASET

    if explicit in {"openfda", "rxnorm", "drugbank", "api"}:
        return RemoteAPIDataSource(explicit)
    if explicit == "json":
        return JSONDataSource(path)
    if explicit == "csv":
        return CSVDataSource(path)
    if explicit in {"sqlite", "db"}:
        return SQLiteDataSource(path)

    # auto: infer from the file extension.
    suffix = Path(path).suffix.lower()
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return SQLiteDataSource(path)
    if suffix == ".csv":
        return CSVDataSource(path)
    return JSONDataSource(path)


# ==========================================================================
# Persistence (async; same contract as the OCR history store)
# ==========================================================================
_engine = create_async_engine(
    settings.INTERACTIONS_DB_URL, echo=False, pool_pre_ping=True, future=True
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
            "Drug-interaction history store ready (%s)",
            settings.INTERACTIONS_DB_URL.split("://")[0],
        )


# ==========================================================================
# Service
# ==========================================================================
class DrugInteractionService:
    """High-level orchestration: load → resolve → analyse → enrich → persist."""

    def __init__(self) -> None:
        self._knowledge: InteractionKnowledge | None = None
        self._load_lock = asyncio.Lock()

    # -- knowledge loading -------------------------------------------------
    async def _get_knowledge(self) -> InteractionKnowledge:
        """Load the knowledge base once (cached for the process lifetime)."""
        if self._knowledge is not None:
            return self._knowledge
        async with self._load_lock:
            if self._knowledge is None:
                source = build_source()
                self._knowledge = await asyncio.to_thread(source.load)
        return self._knowledge

    async def reload(self) -> InteractionKnowledge:
        """Force a re-read of the knowledge base (e.g. after updating the file)."""
        async with self._load_lock:
            source = build_source()
            self._knowledge = await asyncio.to_thread(source.load)
        return self._knowledge

    # -- name resolution ---------------------------------------------------
    def _resolve(self, name: str, knowledge: InteractionKnowledge) -> str | None:
        """Resolve a free-text medicine name to a canonical drug, or None."""
        norm = normalize_name(name)
        if not norm:
            return None
        # 1) exact alias/name hit.
        if norm in knowledge.alias_to_canonical:
            return knowledge.alias_to_canonical[norm]
        # 2) fuzzy fallback against all known aliases/names.
        if _HAS_FUZZY and knowledge.match_keys:
            best = process.extractOne(
                norm, knowledge.match_keys, scorer=fuzz.WRatio
            )
            if best and best[1] >= settings.INTERACTION_MATCH_THRESHOLD:
                return knowledge.alias_to_canonical[best[0]]
        return None

    # -- per-medicine warnings --------------------------------------------
    @staticmethod
    def _warnings_for(
        original: str, canonical: str | None, knowledge: InteractionKnowledge
    ) -> MedicineWarnings:
        display = (canonical or original).title()
        if not canonical:
            return MedicineWarnings(medicine=display, matched=False)
        p = knowledge.profiles.get(canonical, {})
        return MedicineWarnings(
            medicine=display,
            matched=True,
            contraindications=p.get("contraindications", []) or [],
            food=p.get("food", []) or [],
            alcohol=p.get("alcohol", []) or [],
            pregnancy=p.get("pregnancy", []) or [],
            breastfeeding=p.get("breastfeeding", []) or [],
            kidney=p.get("kidney", []) or [],
            liver=p.get("liver", []) or [],
            age_restrictions=p.get("age_restrictions", []) or [],
        )

    # -- analysis ----------------------------------------------------------
    async def analyze(
        self,
        medicines: list[str],
        *,
        include_rag: bool = True,
        persist: bool = True,
        source_record_id: str | None = None,
    ) -> InteractionReport:
        """Run the full interaction analysis for a list of medicine names."""
        names = [m.strip() for m in medicines if m and m.strip()]
        report = InteractionReport(medicines=names)

        if len(names) < 2:
            report.summary = build_summary([], Severity.NONE, len(names))
            report.risk_counts = severity_counts([])
            return report

        knowledge = await self._get_knowledge()

        # Resolve each input name to a canonical drug (preserve order, dedupe).
        resolved: dict[str, str | None] = {}
        for name in names:
            if name not in resolved:
                resolved[name] = self._resolve(name, knowledge)

        report.resolved_medicines = sorted(
            {c for c in resolved.values() if c}
        )
        report.unmatched_medicines = [n for n, c in resolved.items() if not c]

        # Pairwise drug–drug interactions across the resolved drugs.
        interactions: list[DrugDrugInteraction] = []
        canon_pairs = combinations(
            sorted({c for c in resolved.values() if c}), 2
        )
        for a, b in canon_pairs:
            key = InteractionKnowledge.pair_key(
                normalize_name(a), normalize_name(b)
            )
            record = knowledge.pairs.get(key)
            if not record:
                continue
            interactions.append(
                DrugDrugInteraction(
                    medicines=[a.title(), b.title()],
                    severity=coerce_severity(record.get("severity")),
                    clinical_risk=record.get("clinical_risk", ""),
                    explanation=record.get("explanation", ""),
                    recommendation=record.get("recommendation", ""),
                    clinical_notes=record.get("clinical_notes", ""),
                    sources=["dataset"],
                )
            )

        # Sort most-severe first for a sensible UI order.
        interactions.sort(
            key=lambda i: {
                Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MODERATE: 2,
                Severity.LOW: 1, Severity.NONE: 0,
            }[i.severity],
            reverse=True,
        )

        overall = max_severity([i.severity for i in interactions])
        report.interactions = interactions
        report.overall_risk = overall
        report.risk_counts = severity_counts(interactions)
        report.summary = build_summary(interactions, overall, len(names))
        report.recommendations = collect_recommendations(interactions)

        # Per-medicine warnings (food/alcohol/organ/population).
        report.warnings = [
            self._warnings_for(name, resolved[name], knowledge) for name in names
        ]

        # Optional RAG enrichment (best-effort — never breaks the report).
        if include_rag and settings.INTERACTIONS_USE_RAG:
            await self._enrich_with_rag(report)

        # Persist (best-effort — a history failure never breaks analysis).
        if persist:
            report.id = await self._save(report, source_record_id)

        return report

    # -- RAG enrichment ----------------------------------------------------
    async def _enrich_with_rag(self, report: InteractionReport) -> None:
        """Attach knowledge-base context to the report when RAG is available."""
        try:
            from backend.rag.rag_service import get_rag_service

            names = report.resolved_medicines or report.medicines
            if len(names) < 2:
                return
            info = await get_rag_service().amedicine_info(names)
            interactions = info.get("interactions") if isinstance(info, dict) else None
            if interactions and interactions.get("answer"):
                report.rag_notes = interactions["answer"]
                report.rag_sources = interactions.get("sources", []) or []
                report.provider = "local-dataset+rag"
        except Exception as exc:  # noqa: BLE001 — RAG is optional enrichment
            logger.debug("RAG enrichment skipped: %s", exc)

    # -- persistence -------------------------------------------------------
    async def _save(
        self, report: InteractionReport, source_record_id: str | None
    ) -> str | None:
        """Persist one analysis. Best-effort: never raises."""
        try:
            await _ensure_db()
            record_id = uuid.uuid4().hex
            report.id = record_id
            report.created_at = utcnow()

            names = report.resolved_medicines or report.medicines
            row = InteractionRecord(
                id=record_id,
                created_at=report.created_at,
                source_record_id=source_record_id,
                medicines=names,
                medicine_names=",".join(n.lower() for n in names),
                medicine_count=len(report.medicines),
                overall_risk=report.overall_risk.value,
                interaction_count=len(report.interactions),
                summary=report.summary,
                report=report.model_dump(mode="json"),
            )
            async with _Session() as session:
                session.add(row)
                await session.commit()
            logger.info(
                "Saved interaction analysis %s (risk=%s, %d interactions)",
                record_id, report.overall_risk.value, len(report.interactions),
            )
            return record_id
        except Exception:  # noqa: BLE001
            logger.exception("Failed to save interaction analysis")
            return None

    # -- history reads -----------------------------------------------------
    async def list_history(self, *, page: int = 1, page_size: int = 10) -> dict:
        """Return a paginated page of past analyses (newest first)."""
        await _ensure_db()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with _Session() as session:
            total = await session.scalar(select(func.count(InteractionRecord.id))) or 0
            stmt = (
                select(InteractionRecord)
                .order_by(InteractionRecord.created_at.desc())
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
        """Return the full stored report for one analysis, or None if missing."""
        await _ensure_db()
        async with _Session() as session:
            row = await session.get(InteractionRecord, record_id)
            return row.report if row else None

    async def clear_history(self) -> int:
        """Delete every stored analysis. Returns the number removed."""
        await _ensure_db()
        async with _Session() as session:
            count = await session.scalar(select(func.count(InteractionRecord.id))) or 0
            await session.execute(delete(InteractionRecord))
            await session.commit()
        logger.info("Cleared drug-interaction history (%d records)", count)
        return int(count)


# Process-wide singleton (knowledge base is loaded once and cached).
_SERVICE: DrugInteractionService | None = None


def get_service() -> DrugInteractionService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = DrugInteractionService()
    return _SERVICE


# Convenience coroutine used by the OCR pipeline for auto-analysis.
async def analyze_medicines(
    medicines: list[str],
    *,
    include_rag: bool = True,
    persist: bool = True,
    source_record_id: str | None = None,
) -> InteractionReport:
    """Module-level shortcut around :meth:`DrugInteractionService.analyze`."""
    return await get_service().analyze(
        medicines,
        include_rag=include_rag,
        persist=persist,
        source_record_id=source_record_id,
    )
