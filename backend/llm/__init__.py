"""Provider-agnostic LLM layer for the agent system.

Public surface:

* :class:`~backend.llm.base_llm.BaseLLM` — the abstract contract.
* :func:`~backend.llm.factory.get_llm` — resolve the configured provider.
* :func:`~backend.llm.factory.available_providers` — observability descriptor.

The layer is provider-agnostic and offline-safe: with no cloud/local model
configured it transparently uses the deterministic offline provider.
"""

from backend.llm.base_llm import BaseLLM, LLMNotAvailable, LLMResponse
from backend.llm.factory import available_providers, build_llm, get_llm

__all__ = [
    "BaseLLM",
    "LLMResponse",
    "LLMNotAvailable",
    "get_llm",
    "build_llm",
    "available_providers",
]
