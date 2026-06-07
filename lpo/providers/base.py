"""Backend-neutral LLM interface (Section 6.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Raised by adapters for transport/auth/structured-output failures."""


@dataclass
class FormulationResult:
    ir: dict  # parsed LP IR (already schema-valid JSON; not yet semantically checked)
    reasoning: Optional[str] = None  # thinking trace, diagnostic only
    truncated: bool = False  # provider reported a length-based stop
    usage: dict = field(default_factory=dict)  # token counts for logging/cost


@dataclass
class ProviderCapabilities:
    strict_schema: bool  # enforces JSON schema during generation
    reasoning_toggle: bool  # supports a thinking/reasoning mode
    tool_calling: bool  # supports native function calling
    prompt_cache_discount: bool
    max_context: int


@runtime_checkable
class LlmProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def formulate(
        self, messages: list[dict], schema: dict[str, Any]
    ) -> FormulationResult:
        """Return parsed, schema-valid LP IR JSON, or raise ProviderError."""
        ...

    def explain(self, messages: list[dict]) -> str:
        """Return prose narration of a SolverResult."""
        ...
