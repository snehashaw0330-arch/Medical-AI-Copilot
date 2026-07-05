"""Abstract LLM interface — the provider-agnostic contract every model implements.

The whole agent layer depends only on :class:`BaseLLM`, never on a concrete SDK.
That is the Dependency-Inversion pillar of this design: business logic (agents)
talks to an abstraction, and providers (OpenAI, Gemini, Claude, Ollama, …) are
plugged in behind it via the factory. Adding a new provider therefore never
requires touching an agent.

Every provider must:

* report whether it is usable right now (:meth:`available`) — driven by config +
  installed SDK + reachable endpoint, so the app runs with *no* cloud LLM, and
* implement a single async completion primitive (:meth:`acomplete`).

An always-available :class:`~backend.llm.providers.offline.OfflineLLM` guarantees
the system degrades gracefully when nothing is configured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LLMNotAvailable(RuntimeError):
    """Raised when a provider is selected but cannot service a request."""


@dataclass
class LLMResponse:
    """Uniform completion result returned by every provider."""

    text: str
    provider: str
    model: str = ""
    usage: dict = field(default_factory=dict)
    raw: object = None


class BaseLLM(ABC):
    """Provider-agnostic async LLM. Concrete providers subclass this."""

    #: Stable provider key (matches the factory registry + config values).
    name: str = "base"

    def __init__(self, model: str = "", **options) -> None:
        self.model = model
        self.options = options

    @abstractmethod
    def available(self) -> bool:
        """True when this provider can actually service a request right now."""

    @abstractmethod
    async def acomplete(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        """Return a completion for ``prompt`` given a ``system`` instruction."""

    async def asummarize(self, text: str, instruction: str = "Summarise concisely:") -> str:
        """Convenience helper used by agents that only need a short summary."""
        resp = await self.acomplete(
            system="You are a careful medical writing assistant. Never invent facts.",
            prompt=f"{instruction}\n\n{text}",
            temperature=0.1,
            max_tokens=400,
        )
        return resp.text

    def info(self) -> dict:
        """Small descriptor for observability / the registry endpoint."""
        return {"provider": self.name, "model": self.model, "available": self.available()}
