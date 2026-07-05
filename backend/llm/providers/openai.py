"""OpenAI (and OpenAI-compatible) chat-completions provider.

Concrete, working implementation against the official ``openai`` async SDK. It is
also the base for any OpenAI-compatible endpoint (DeepSeek, OpenRouter, local
vLLM …) — those only differ by ``base_url``/model, so they subclass this rather
than duplicating the request logic (DRY).
"""

from __future__ import annotations

from backend.llm.base_llm import BaseLLM, LLMNotAvailable, LLMResponse


class OpenAILLM(BaseLLM):
    """OpenAI Chat Completions provider (async)."""

    name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        **options,
    ) -> None:
        super().__init__(model=model, **options)
        self.api_key = api_key
        self.base_url = base_url
        try:  # SDK is optional — absence simply makes the provider unavailable.
            from openai import AsyncOpenAI  # type: ignore

            self._client_cls = AsyncOpenAI
        except Exception:  # noqa: BLE001
            self._client_cls = None

    def available(self) -> bool:
        return bool(self.api_key and self._client_cls)

    async def acomplete(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        if not self.available():
            raise LLMNotAvailable(f"{self.name}: missing API key or SDK")
        client = self._client_cls(api_key=self.api_key, base_url=self.base_url)
        resp = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            usage=usage.model_dump() if hasattr(usage, "model_dump") else {},
        )
