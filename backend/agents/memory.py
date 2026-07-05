"""Shared memory — the blackboard agents collaborate through.

Each run owns one :class:`SharedMemory`. Agents read their inputs from it and
write their outputs back under well-known keys (see
:class:`~backend.agents.context_manager.MemoryKeys`). This is how the pipeline
composes without agents calling each other directly:

    OCR      → writes  ocr_result
    Medicine → reads   ocr_result / inputs.medicines, writes medicines
    Disease  → reads   inputs.symptoms, writes disease
    Clinical → reads   everything, writes clinical
    Report   → reads   everything, writes report

Access is guarded by an async lock because agents in the same workflow *stage*
run concurrently. They write disjoint keys by design, but the lock makes the
store safe regardless.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any


class SharedMemory:
    """An async-safe key/value blackboard for one workflow run."""

    def __init__(self, seed: dict[str, Any] | None = None) -> None:
        self._store: dict[str, Any] = dict(seed or {})
        self._lock = asyncio.Lock()

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._store.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._store[key] = value

    async def update(self, key: str, patch: dict) -> None:
        """Merge ``patch`` into the dict stored at ``key`` (created if absent)."""
        async with self._lock:
            current = self._store.get(key)
            if not isinstance(current, dict):
                current = {}
            current.update(patch)
            self._store[key] = current

    async def has(self, key: str) -> bool:
        async with self._lock:
            return key in self._store

    async def snapshot(self) -> dict[str, Any]:
        """A deep copy of the whole store (safe to serialise/inspect)."""
        async with self._lock:
            try:
                return copy.deepcopy(self._store)
            except Exception:  # noqa: BLE001 — fall back to a shallow copy
                return dict(self._store)

    # Sync convenience for read-only inspection after a run (no await needed).
    def peek(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)
