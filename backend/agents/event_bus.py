"""Async event bus — the backbone of the event-driven agent workflow.

A minimal, dependency-free publish/subscribe hub. The workflow engine publishes
lifecycle events (workflow/agent started, completed, failed, log); subscribers —
the run store (for the live monitor) and any future consumer (metrics, webhooks)
— react without the engine knowing who is listening. This decoupling is the
event-driven part of the architecture and keeps components single-responsibility.

Handlers may be sync or async; both are supported. A failing handler is isolated
so one bad subscriber never breaks the workflow or other subscribers.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from backend.agents.logger import get_logger
from backend.agents.schemas import EventType

logger = get_logger("event_bus")

Handler = Callable[["Event"], Awaitable[None] | None]


class Event:
    """An immutable-ish message flowing through the bus."""

    __slots__ = ("type", "run_id", "agent", "message", "timestamp", "payload")

    def __init__(
        self,
        type: EventType,
        run_id: str,
        agent: str | None = None,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.type = type
        self.run_id = run_id
        self.agent = agent
        self.message = message
        self.timestamp = datetime.now(timezone.utc)
        self.payload = payload or {}


class AsyncEventBus:
    """Simple async pub/sub. One process-wide instance is used by the app."""

    def __init__(self) -> None:
        self._subscribers: list[Handler] = []

    def subscribe(self, handler: Handler) -> Callable[[], None]:
        """Register a handler. Returns an unsubscribe callable."""
        self._subscribers.append(handler)

        def _unsub() -> None:
            try:
                self._subscribers.remove(handler)
            except ValueError:
                pass

        return _unsub

    async def publish(self, event: Event) -> None:
        """Deliver an event to every subscriber (failures isolated)."""
        for handler in list(self._subscribers):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:  # noqa: BLE001 — a subscriber must never break the bus
                logger.exception("Event subscriber failed for %s", event.type)

    async def emit(
        self,
        type: EventType,
        run_id: str,
        agent: str | None = None,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Convenience: build + publish an event in one call."""
        await self.publish(Event(type, run_id, agent, message, payload))


# Process-wide singleton bus.
_BUS: AsyncEventBus | None = None


def get_event_bus() -> AsyncEventBus:
    global _BUS
    if _BUS is None:
        _BUS = AsyncEventBus()
    return _BUS
