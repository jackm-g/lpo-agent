"""Provider layer (Section 6.6): the only code that talks to an LLM API.

Nothing outside this package imports a vendor SDK or knows a model ID. Selecting
a provider is a configuration change confined here.
"""

from __future__ import annotations

from ..config import Config
from .base import (
    FormulationResult,
    LlmProvider,
    ProviderCapabilities,
    ProviderError,
)
from .fireworks import FireworksProvider
from .mock import MockProvider


def get_provider(config: Config) -> LlmProvider:
    """Return the single configured provider (Section 3: exactly one active)."""

    name = config.provider.lower()
    if name == "fireworks":
        return FireworksProvider(config)
    if name == "mock":
        return MockProvider(config)
    raise ProviderError(
        f"Unknown provider {config.provider!r}. Configured providers: fireworks, mock."
    )


__all__ = [
    "FormulationResult",
    "LlmProvider",
    "ProviderCapabilities",
    "ProviderError",
    "FireworksProvider",
    "MockProvider",
    "get_provider",
]
