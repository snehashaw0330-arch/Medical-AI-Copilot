"""Agent health monitor — lightweight, cached liveness probes per agent.

Distinct from :meth:`AgentRegistry.is_enabled` (administrative on/off via
config): this actually probes whether each agent's underlying dependency
works right now — the RAG index loads, the disease model file is present,
the interaction dataset parses, the OCR stack imports — without running the
agent's full pipeline logic. Each agent declares its own probe via
:meth:`BaseAgent.health_check`; this module just calls them, isolates
failures, and caches results briefly so `/agents/health` and the frontend's
Agent Status Dashboard can poll it often without repeated I/O.
"""

from __future__ import annotations

import asyncio
import time

from backend.agents.agent_registry import AGENT_SPECS, AgentRegistry
from backend.agents.logger import get_logger
from backend.agents.schemas import AgentHealth, HealthReport

logger = get_logger("health_monitor")

# How long a probe result is trusted before being re-checked.
_CACHE_TTL = 30.0  # seconds


class AgentHealthMonitor:
    """Probes every registered agent's dependency and caches the result briefly."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self._registry = registry or AgentRegistry()
        self._cache: dict[str, tuple[float, AgentHealth]] = {}
        self._lock = asyncio.Lock()

    async def check(self, name: str, *, force: bool = False) -> AgentHealth:
        """Health of one agent (cached within :data:`_CACHE_TTL`)."""
        now = time.monotonic()
        if not force:
            cached = self._cache.get(name)
            if cached and now - cached[0] < _CACHE_TTL:
                return cached[1]

        spec = AGENT_SPECS.get(name)
        if spec is None:
            return AgentHealth(name=name, title=name, healthy=False, enabled=False,
                                detail="Unknown agent.")

        if not self._registry.is_enabled(name):
            health = AgentHealth(name=name, title=spec.title, healthy=False, enabled=False,
                                  detail="Disabled via AGENTS_DISABLED configuration.")
        else:
            try:
                agent = self._registry.get(name)
                healthy, detail = await agent.health_check()
                health = AgentHealth(name=name, title=spec.title, healthy=bool(healthy),
                                      enabled=True, detail=detail)
            except Exception as exc:  # noqa: BLE001 — a broken probe reports unhealthy, never crashes
                logger.warning("Health probe failed for %s: %s", name, exc)
                health = AgentHealth(name=name, title=spec.title, healthy=False, enabled=True,
                                      detail=f"Probe raised: {exc}")

        async with self._lock:
            self._cache[name] = (now, health)
        return health

    async def check_all(self, *, force: bool = False) -> HealthReport:
        """Health of every registered agent + an aggregate status."""
        from backend.llm.factory import get_llm

        results = await asyncio.gather(*(self.check(name, force=force) for name in AGENT_SPECS))
        healthy_count = sum(1 for r in results if r.healthy)
        enabled_count = sum(1 for r in results if r.enabled)
        total = len(results)
        status = "ok" if healthy_count == total else ("degraded" if healthy_count else "down")
        return HealthReport(
            status=status,
            total_agents=total,
            healthy_agents=healthy_count,
            enabled_agents=enabled_count,
            llm_provider=get_llm().name,
            agents=list(results),
        )


_MONITOR: AgentHealthMonitor | None = None


def get_health_monitor() -> AgentHealthMonitor:
    global _MONITOR
    if _MONITOR is None:
        _MONITOR = AgentHealthMonitor()
    return _MONITOR
