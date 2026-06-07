"""Formulation service (Section 6.1).

The only component that prompts the model for a *model*. Output is
schema-constrained at the provider; here we parse it into the typed LP IR and
detect truncation. Semantic validation lives in :mod:`lpo.validation`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import LpIr, lp_ir_schema
from .providers.base import LlmProvider
from .validation import coerce_ir


@dataclass
class FormulationOutcome:
    ir: Optional[LpIr]
    reasoning: Optional[str]
    truncated: bool
    schema_errors: list[str]
    usage: dict


def formulate(provider: LlmProvider, messages: list[dict]) -> FormulationOutcome:
    """Call the provider and parse its output into an LP IR.

    Truncation is treated as a (recoverable) failure: a length-stopped payload
    may be invalid even under schema mode (Section 6.1 / 8).
    """

    result = provider.formulate(messages, lp_ir_schema())
    ir, errors = coerce_ir(result.ir)

    if result.truncated and ir is None:
        errors = errors or ["Output was truncated (finish_reason=length)."]

    return FormulationOutcome(
        ir=ir,
        reasoning=result.reasoning,
        truncated=result.truncated,
        schema_errors=errors,
        usage=result.usage,
    )
