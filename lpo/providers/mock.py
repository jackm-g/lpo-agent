"""Offline mock provider.

Lets the whole pipeline run and be tested without network access or an API key.
It is *not* a real model: it pattern-matches the question or replays a scripted
queue of IRs, and narrates SolverResults deterministically from their numbers
(so the explanation-faithfulness check in Section 11 holds).

Select it with ``LPO_PROVIDER=mock``.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..config import Config
from .base import FormulationResult, ProviderCapabilities

# The recon/resupply worked instance (Section 5.1) — the canonical golden.
RECON_IR: dict[str, Any] = {
    "status": "formulated",
    "sense": "maximize",
    "variables": [
        {"name": "x1", "meaning": "recon sorties", "lower": 0, "upper": None, "integer": True},
        {"name": "x2", "meaning": "resupply sorties", "lower": 0, "upper": None, "integer": True},
    ],
    "objective": [{"var": "x1", "coef": 3}, {"var": "x2", "coef": 5}],
    "constraints": [
        {"name": "airframes", "terms": [{"var": "x1", "coef": 1}], "op": "<=", "rhs": 4,
         "source": "4 ISR airframe-days; recon uses one each"},
        {"name": "fuel", "terms": [{"var": "x2", "coef": 2}], "op": "<=", "rhs": 12,
         "source": "resupply burns 2 fuel pallets each, 12 available"},
        {"name": "aircrew", "terms": [{"var": "x1", "coef": 3}, {"var": "x2", "coef": 2}],
         "op": "<=", "rhs": 18, "source": "duty hours: recon 3, resupply 2, 18 total"},
    ],
}

NEED_INFO_IR: dict[str, Any] = {
    "status": "need_info",
    "need_info": "What are the per-unit profits and the resource limits? I need "
    "concrete numbers before I can formulate a model.",
    "sense": "maximize",
    "variables": [{"name": "x1", "meaning": "placeholder", "lower": 0, "integer": False}],
    "objective": [{"var": "x1", "coef": 1}],
    "constraints": [],
}


class MockProvider:
    name = "mock"
    capabilities = ProviderCapabilities(
        strict_schema=True,
        reasoning_toggle=False,
        tool_calling=False,
        prompt_cache_discount=False,
        max_context=32_000,
    )

    def __init__(self, config: Optional[Config] = None, scripted_irs: Optional[list[dict]] = None):
        self.config = config
        # When provided, formulate() pops these in order (for recovery-loop tests).
        self._scripted = list(scripted_irs or [])

    def formulate(self, messages: list[dict], schema: dict[str, Any]) -> FormulationResult:
        if self._scripted:
            return FormulationResult(ir=self._scripted.pop(0), reasoning="(scripted)", usage={})

        # Inspect only the real user question — NOT the few-shot examples in the
        # system/seed turns, which also mention recon/resupply.
        question = _last_user(messages).lower()
        if any(k in question for k in ("recon", "resupply", "sortie", "airframe")):
            ir = json.loads(json.dumps(RECON_IR))  # deep copy
        else:
            # No concrete numbers to formulate from — the honest move is to ask.
            ir = json.loads(json.dumps(NEED_INFO_IR))
        return FormulationResult(ir=ir, reasoning="(mock heuristic)", usage={})

    def explain(self, messages: list[dict]) -> str:
        result = _extract_solver_result(messages)
        if result is None:
            return "No solver result was available to explain."
        return _narrate(result)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _extract_solver_result(messages: list[dict]) -> Optional[dict]:
    """Pull the SolverResult JSON the explanation builder embedded (Section 6.4)."""

    for m in reversed(messages):
        content = m.get("content", "")
        marker = "SOLVER_RESULT_JSON:"
        if marker in content:
            blob = content.split(marker, 1)[1].strip()
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                # Tolerate trailing prose after the JSON object.
                return json.loads(blob[: blob.rfind("}") + 1])
    return None


def _narrate(result: dict) -> str:
    """Deterministic, grounded narrative. Every number comes from `result`."""

    if result.get("status") != "optimal":
        return f"The model is {result.get('status')}; no optimal decision exists."

    parts: list[str] = []
    decisions = ", ".join(f"{k} = {v}" for k, v in result.get("variables", {}).items())
    parts.append(
        f"Optimal objective value is {result.get('objective_value')}, achieved at {decisions}."
    )

    binding = [c for c in result.get("constraints", []) if c.get("binding")]
    slack = [c for c in result.get("constraints", []) if not c.get("binding")]
    if binding:
        names = ", ".join(c["name"] for c in binding)
        parts.append(f"Binding constraints (the bottlenecks): {names}.")
        for c in binding:
            sp = c.get("shadow_price")
            if sp is not None:
                basis = c.get("shadow_price_basis")
                caveat = (
                    " (LP-relaxation directional indicator, not an exact integer "
                    "marginal value)"
                    if basis == "lp_relaxation"
                    else ""
                )
                parts.append(
                    f"Shadow price for {c['name']} is {sp}{caveat}, with slack {c.get('slack')}."
                )
    if slack:
        names = ", ".join(f"{c['name']} (slack {c.get('slack')})" for c in slack)
        parts.append(f"Non-binding constraints with room to spare: {names}.")
    return " ".join(parts)
