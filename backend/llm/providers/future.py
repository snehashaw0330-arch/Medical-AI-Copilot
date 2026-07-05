"""Extension template for FUTURE providers (OpenRouter, Mistral, MCP, …).

This file documents *the only steps* needed to add a provider, proving the
architecture is Open-Closed: new models plug in here (or in a sibling file) and
register in the factory — no agent or workflow code changes.

Examples of what slots in here without touching business logic:

* **OpenRouter / Mistral / Together** — OpenAI-compatible: subclass
  :class:`~backend.llm.providers.openai.OpenAILLM` with the right ``base_url``
  (mirroring :class:`~backend.llm.providers.deepseek.DeepSeekLLM`).
* **Model Context Protocol (MCP)** — implement :meth:`acomplete` by proxying to
  an MCP server/tool; keep the same :class:`BaseLLM` contract.
* **Bespoke / on-prem inference** — implement the two abstract methods.
"""

from __future__ import annotations

from backend.llm.base_llm import BaseLLM, LLMNotAvailable, LLMResponse


class FutureLLM(BaseLLM):
    """A registered-but-unconfigured placeholder provider.

    It is intentionally *unavailable* so the factory transparently falls back to
    the offline provider until a real implementation is dropped in. Replace the
    body of :meth:`acomplete` (and :meth:`available`) to activate it.
    """

    name = "future"

    def available(self) -> bool:
        return False

    async def acomplete(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        raise LLMNotAvailable(
            "future: not implemented — subclass BaseLLM or OpenAILLM and register "
            "it in backend/llm/factory.py::_PROVIDERS"
        )
