"""Evaluation helpers (Section 11).

- IR equivalence that is invariant to variable *names* and constraint *order*
  (compares structure by variable *meaning*).
- Solver-correctness check by re-substituting the returned solution into every
  constraint.
- Explanation faithfulness reuses :func:`lpo.explanation.grounded_numbers`.
"""

from __future__ import annotations

from typing import Any

from .explanation import grounded_numbers  # noqa: F401  (re-exported for evals)
from .models import LpIr, SolverResult

CONSTRAINT_TOL = 1e-6


def ir_signature(ir: LpIr) -> dict[str, Any]:
    """A canonical, name- and order-invariant signature of an LP IR.

    Variables are keyed by their `meaning` (normalized), so two IRs that differ
    only in variable names (x1 vs recon) and constraint ordering compare equal.
    """

    name_to_meaning = {v.name: _norm_text(v.meaning) for v in ir.variables}

    def term_key(t):
        return (name_to_meaning.get(t.var, t.var), float(t.coef))

    variables = sorted(
        (
            _norm_text(v.meaning),
            _num(v.lower),
            _num(v.upper),
            bool(v.integer),
        )
        for v in ir.variables
    )
    objective = sorted(term_key(t) for t in ir.objective)
    constraints = sorted(
        (
            tuple(sorted(term_key(t) for t in c.terms)),
            c.op,
            float(c.rhs),
        )
        for c in ir.constraints
    )
    return {
        "sense": ir.sense,
        "variables": variables,
        "objective": objective,
        "constraints": constraints,
    }


def ir_equivalent(a: LpIr, b: LpIr) -> bool:
    return ir_signature(a) == ir_signature(b)


def solution_satisfies_constraints(ir: LpIr, result: SolverResult) -> list[str]:
    """Re-substitute the returned solution into every constraint (Section 11).

    Returns a list of violation messages; empty means the solution is feasible.
    """

    violations: list[str] = []
    x = result.variables
    for c in ir.constraints:
        lhs = sum(t.coef * x.get(t.var, 0.0) for t in c.terms)
        if c.op == "<=" and lhs > c.rhs + CONSTRAINT_TOL:
            violations.append(f"{c.name}: {lhs} <= {c.rhs} violated")
        elif c.op == ">=" and lhs < c.rhs - CONSTRAINT_TOL:
            violations.append(f"{c.name}: {lhs} >= {c.rhs} violated")
        elif c.op == "==" and abs(lhs - c.rhs) > CONSTRAINT_TOL:
            violations.append(f"{c.name}: {lhs} == {c.rhs} violated")
    # Bounds.
    bounds = {v.name: (v.lower, v.upper) for v in ir.variables}
    for name, val in x.items():
        lo, hi = bounds.get(name, (None, None))
        if lo is not None and val < lo - CONSTRAINT_TOL:
            violations.append(f"{name}={val} below lower bound {lo}")
        if hi is not None and val > hi + CONSTRAINT_TOL:
            violations.append(f"{name}={val} above upper bound {hi}")
    return violations


def _norm_text(s: str) -> str:
    return " ".join(s.lower().split())


def _num(x):
    return None if x is None else float(x)
