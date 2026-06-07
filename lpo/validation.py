"""Deterministic validation layer (Section 6.2). Pure functions, no network.

Schema-constrained generation guarantees *syntax*; this layer is the first line
against *semantic* malformations the schema cannot catch (dangling variable
references, duplicate names, inverted bounds, smuggled nonlinearity).
"""

from __future__ import annotations

import math
from typing import Iterable

from pydantic import ValidationError

from .models import LpIr


class ValidationFinding:
    """An advisory finding (e.g. provenance gaps) surfaced to a human reviewer."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"ValidationFinding({self.code!r}, {self.message!r})"


def validate(ir: LpIr) -> list[str]:
    """Return a list of blocking errors. Empty list means the IR is valid.

    The error strings are designed to be fed straight back to the formulation
    model as a correction turn (Section 6.5).
    """

    errors: list[str] = []

    var_names = [v.name for v in ir.variables]
    declared = set(var_names)

    # 5. Uniqueness — variable names.
    for dup in _duplicates(var_names):
        errors.append(f"Duplicate variable name '{dup}'. Variable names must be unique.")

    # 5. Uniqueness — constraint names.
    for dup in _duplicates([c.name for c in ir.constraints]):
        errors.append(f"Duplicate constraint name '{dup}'. Constraint names must be unique.")

    # 3. Numeric sanity — bounds.
    for v in ir.variables:
        if v.lower is not None and not math.isfinite(v.lower):
            errors.append(f"Variable '{v.name}' has a non-finite lower bound.")
        if v.upper is not None and not math.isfinite(v.upper):
            errors.append(f"Variable '{v.name}' has a non-finite upper bound.")
        if (
            v.lower is not None
            and v.upper is not None
            and v.lower > v.upper
        ):
            errors.append(
                f"Variable '{v.name}' has lower={v.lower} > upper={v.upper}."
            )

    # 2. Reference integrity + 3. numeric sanity — objective.
    if not ir.objective:
        errors.append("Objective is empty; at least one objective term is required.")
    for t in ir.objective:
        if t.var not in declared:
            errors.append(
                f"Objective references undeclared variable '{t.var}'."
            )
        if not math.isfinite(t.coef):
            errors.append(f"Objective coefficient for '{t.var}' is not finite.")

    # 2. Reference integrity + 3. numeric sanity — constraints.
    for c in ir.constraints:
        if not math.isfinite(c.rhs):
            errors.append(f"Constraint '{c.name}' has a non-finite RHS.")
        seen_terms: set[str] = set()
        for t in c.terms:
            if t.var not in declared:
                errors.append(
                    f"Constraint '{c.name}' references undeclared variable '{t.var}'."
                )
            if not math.isfinite(t.coef):
                errors.append(
                    f"Constraint '{c.name}' has a non-finite coefficient on '{t.var}'."
                )
            # 7. Linearity: a variable repeated in one constraint's terms is the
            # most common way a nonlinear/aggregation error sneaks in.
            if t.var in seen_terms:
                errors.append(
                    f"Constraint '{c.name}' lists variable '{t.var}' more than once; "
                    f"combine it into a single linear term."
                )
            seen_terms.add(t.var)

    return errors


def provenance_findings(ir: LpIr) -> list[ValidationFinding]:
    """Advisory provenance check (Section 6.2 item 6). Non-blocking.

    Flags any constraint whose `source` is empty/whitespace. A fuller heuristic
    (requirements in the question with no citing constraint) is left to the human
    restatement gate, which is the real provenance backstop.
    """

    findings: list[ValidationFinding] = []
    for c in ir.constraints:
        if not c.source or not c.source.strip():
            findings.append(
                ValidationFinding(
                    "missing_source",
                    f"Constraint '{c.name}' has no source span justifying it.",
                )
            )
    return findings


def coerce_ir(raw: dict) -> tuple[LpIr | None, list[str]]:
    """Parse provider JSON into an LpIr. Schema errors become blocking strings.

    This is the 'redundant with constrained generation, cheap insurance' check
    (Section 6.2 item 1) that guards against provider edge cases and truncation.
    """

    try:
        return LpIr.model_validate(raw), []
    except ValidationError as exc:
        return None, [f"Schema violation: {e['loc']}: {e['msg']}" for e in exc.errors()]


# --------------------------------------------------------------------------- #
# Restatement (Section 6.2 — the human confirmation gate)                      #
# --------------------------------------------------------------------------- #
def restate(ir: LpIr) -> str:
    """Render the IR into one plain-language paragraph for human review.

    The single highest-leverage guardrail against a well-formed but wrong model:
    a reviewer catches a flipped inequality in seconds.
    """

    meaning = {v.name: v.meaning for v in ir.variables}
    sense_word = "maximize" if ir.sense == "maximize" else "minimize"

    obj = _join_terms(ir.objective, meaning)
    lines = [f"We want to {sense_word} {obj}, by choosing:"]
    for v in ir.variables:
        kind = "integer" if v.integer else "continuous"
        bound = _describe_bounds(v.lower, v.upper)
        lines.append(f"  - {v.name} = {v.meaning} ({kind}{bound}).")

    if ir.constraints:
        lines.append("Subject to:")
        op_word = {"<=": "at most", ">=": "at least", "==": "exactly"}
        for c in ir.constraints:
            lhs = _join_terms(c.terms, meaning)
            lines.append(
                f"  - {c.name}: {lhs} must be {op_word[c.op]} {_fmt(c.rhs)} "
                f"[because: {c.source}]."
            )
    else:
        lines.append("Subject to no explicit constraints.")
    return "\n".join(lines)


def _join_terms(terms, meaning: dict[str, str]) -> str:
    pieces = []
    for t in terms:
        label = meaning.get(t.var, t.var)
        pieces.append(f"{_fmt(t.coef)}×({label})")
    return " + ".join(pieces)


def _describe_bounds(lower, upper) -> str:
    if lower is None and upper is None:
        return ", unbounded"
    if lower is not None and upper is None:
        return f", ≥ {_fmt(lower)}"
    if lower is None and upper is not None:
        return f", ≤ {_fmt(upper)}"
    return f", in [{_fmt(lower)}, {_fmt(upper)}]"


def _fmt(x: float) -> str:
    if x == int(x):
        return str(int(x))
    return str(x)


def _duplicates(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    dups: list[str] = []
    for it in items:
        if it in seen and it not in dups:
            dups.append(it)
        seen.add(it)
    return dups
