"""Ollama provider — local, self-hosted models (Llama, Mistral, …), no API key.

Talks to a local Ollama server over HTTP, so it needs no cloud account. This is
the recommended path for fully-offline/on-prem deployments.
"""

from __future__ import annotations

from backend.llm.base_llm import BaseLLM, LLMNotAvailable, LLMResponse


class OllamaLLM(BaseLLM):
    """Local Ollama chat provider (Llama/Mistral/etc.)."""

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
        **options,
    ) -> None:
        super().__init__(model=model, **options)
        self.base_url = base_url.rstrip("/")
        try:
            import httpx  # type: ignore

            self._httpx = httpx
        except Exception:  # noqa: BLE001
            self._httpx = None

    def available(self) -> bool:
        # httpx must be installed AND the server must be reachable — otherwise the
        # "auto" selector would pick a dead endpoint. A short TCP probe keeps this
        # cheap (connection-refused is immediate on a down localhost server).
        if not self._httpx:
            return False
        return self._reachable()

    def _reachable(self) -> bool:
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(self.base_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 11434
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            return False

    async def acomplete(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        if not self.available():
            raise LLMNotAvailable(f"{self.name}: httpx not installed")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with self._httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 — surface as not-available for fallback
            raise LLMNotAvailable(f"{self.name}: {exc}") from exc
        text = (data.get("message", {}) or {}).get("content", "").strip()
        return LLMResponse(text=text, provider=self.name, model=self.model, raw=data)
