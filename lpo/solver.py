"""Solver service (Section 6.3). Deterministic. Wraps HiGHS via PuLP.

The solver is the source of truth for every number downstream (Section 7.4):
the model never computes. This module extracts the primal solution, per-
constraint slack/binding flags, dual (shadow) prices with an explicit basis
label, and a diagnosis (IIS or unbounded ray) when there is no optimum.
"""

from __future__ import annotations

from typing import Optional

import pulp

from .models import (
    Constraint,
    ConstraintResult,
    Diagnosis,
    LpIr,
    SolverResult,
)

BINDING_TOL = 1e-6

_STATUS_MAP = {
    pulp.LpStatusOptimal: "optimal",
    pulp.LpStatusInfeasible: "infeasible",
    pulp.LpStatusUnbounded: "unbounded",
    pulp.LpStatusNotSolved: "error",
    pulp.LpStatusUndefined: "error",
}


def _solver(msg: bool = False):
    """Prefer HiGHS (Section 6.3); fall back to bundled CBC if unavailable."""

    for factory in (
        lambda: pulp.HiGHS(msg=msg),
        lambda: pulp.HiGHS_CMD(msg=msg),
        lambda: pulp.PULP_CBC_CMD(msg=msg),
    ):
        try:
            s = factory()
            if s.available():
                return s
        except Exception:
            continue
    return pulp.PULP_CBC_CMD(msg=msg)


def solve(ir: LpIr) -> SolverResult:
    is_integer = any(v.integer for v in ir.variables)
    try:
        prob, variables, con_objs = _build(ir, relax=False)
        prob.solve(_solver())
        status = _STATUS_MAP.get(prob.status, "error")
    except Exception as exc:  # pragma: no cover - solver/runtime failure
        return SolverResult(status="error", is_integer_model=is_integer, error=str(exc))

    if status == "infeasible":
        return SolverResult(
            status="infeasible",
            is_integer_model=is_integer,
            diagnosis=_diagnose_infeasible(ir),
        )
    if status == "unbounded":
        return SolverResult(
            status="unbounded",
            is_integer_model=is_integer,
            diagnosis=_diagnose_unbounded(ir),
        )
    if status != "optimal":
        return SolverResult(
            status="error",
            is_integer_model=is_integer,
            error=f"Solver returned status '{pulp.LpStatus[prob.status]}'.",
        )

    # ---- Extract the primal solution -------------------------------------- #
    var_values: dict[str, float] = {}
    int_flag = {v.name: v.integer for v in ir.variables}
    for name, pv in variables.items():
        val = pv.value()
        val = 0.0 if val is None else float(val)
        if int_flag[name]:
            val = round(val)
        var_values[name] = val

    objective_value = float(pulp.value(prob.objective))

    # ---- Shadow prices (Section 7.3) -------------------------------------- #
    # Duality is undefined for integer programs, so for a MILP we report the LP
    # relaxation's duals, explicitly labelled. We compute them as dObjective/d(rhs)
    # by finite difference on the continuous problem, which fixes the marginal
    # value to a sign-correct, backend-independent convention (solver dual signs
    # vary). For a genuinely continuous model this is the exact LP dual.
    duals = _shadow_prices(ir)
    basis = "lp_relaxation" if is_integer else "lp"

    constraints = [
        _constraint_result(c, var_values, duals.get(c.name), basis)
        for c in ir.constraints
    ]

    return SolverResult(
        status="optimal",
        is_integer_model=is_integer,
        objective_value=objective_value,
        variables=var_values,
        constraints=constraints,
        sensitivity=None,  # RHS/cost ranging is a Phase-4 enhancement (Section 14).
    )


# --------------------------------------------------------------------------- #
# Model construction                                                           #
# --------------------------------------------------------------------------- #
def _build(ir: LpIr, relax: bool, subset: Optional[list[Constraint]] = None):
    """Return (problem, {name: LpVariable}, {name: constraint-object})."""

    sense = pulp.LpMaximize if ir.sense == "maximize" else pulp.LpMinimize
    prob = pulp.LpProblem("lpo", sense)

    variables: dict[str, pulp.LpVariable] = {}
    for v in ir.variables:
        cat = pulp.LpInteger if (v.integer and not relax) else pulp.LpContinuous
        variables[v.name] = pulp.LpVariable(
            v.name, lowBound=v.lower, upBound=v.upper, cat=cat
        )

    prob += pulp.lpSum(t.coef * variables[t.var] for t in ir.objective), "objective"

    con_objs = {}
    for c in subset if subset is not None else ir.constraints:
        expr = pulp.lpSum(t.coef * variables[t.var] for t in c.terms)
        if c.op == "<=":
            constraint = expr <= c.rhs
        elif c.op == ">=":
            constraint = expr >= c.rhs
        else:
            constraint = expr == c.rhs
        prob += constraint, c.name
        con_objs[c.name] = prob.constraints[c.name]
    return prob, variables, con_objs


def _constraint_result(
    c: Constraint,
    var_values: dict[str, float],
    shadow_price: Optional[float],
    basis: str,
) -> ConstraintResult:
    lhs = sum(t.coef * var_values.get(t.var, 0.0) for t in c.terms)
    if c.op == "<=":
        slack = c.rhs - lhs
    elif c.op == ">=":
        slack = lhs - c.rhs
    else:  # ==
        slack = abs(lhs - c.rhs)
    binding = abs(slack) <= BINDING_TOL or c.op == "=="

    # Shadow prices come from a finite-difference quotient (delta = 1e-4), so the
    # last few digits are numerical noise; round to 6 decimals for a clean,
    # honest read (e.g. 0.749999999 -> 0.75).
    sp = None if shadow_price is None else round(float(shadow_price), 6)
    return ConstraintResult(
        name=c.name,
        lhs_value=round(lhs, 9),
        rhs=c.rhs,
        binding=binding,
        slack=round(slack, 9),
        shadow_price=sp,
        shadow_price_basis=basis if sp is not None else "none",
    )


# --------------------------------------------------------------------------- #
# Diagnosis                                                                    #
# --------------------------------------------------------------------------- #
_FD_DELTA = 1e-4


def _relaxed_optimum(ir: LpIr, rhs_overrides: Optional[dict[str, float]] = None):
    """Solve the LP relaxation, optionally overriding some constraint RHSs.

    Returns the optimal objective value, or None if not optimal.
    """

    sense = pulp.LpMaximize if ir.sense == "maximize" else pulp.LpMinimize
    prob = pulp.LpProblem("relax", sense)
    variables = {
        v.name: pulp.LpVariable(v.name, lowBound=v.lower, upBound=v.upper)
        for v in ir.variables
    }
    prob += pulp.lpSum(t.coef * variables[t.var] for t in ir.objective), "objective"
    overrides = rhs_overrides or {}
    for c in ir.constraints:
        expr = pulp.lpSum(t.coef * variables[t.var] for t in c.terms)
        rhs = overrides.get(c.name, c.rhs)
        if c.op == "<=":
            prob += expr <= rhs, c.name
        elif c.op == ">=":
            prob += expr >= rhs, c.name
        else:
            prob += expr == rhs, c.name
    prob.solve(_solver())
    if prob.status != pulp.LpStatusOptimal:
        return None
    return float(pulp.value(prob.objective))


def _shadow_prices(ir: LpIr) -> dict[str, Optional[float]]:
    """Per-constraint dObjective/d(rhs) via finite difference on the LP relaxation.

    Standard shadow-price definition: the marginal change in the optimal
    objective per unit increase of a constraint's right-hand side. Computed on
    the continuous (relaxed) problem; for integer models this is the
    relaxation-based directional indicator of Section 7.3, not an exact integer
    marginal value.
    """

    base = _relaxed_optimum(ir)
    if base is None:
        return {}

    prices: dict[str, Optional[float]] = {}
    for c in ir.constraints:
        try:
            bumped = _relaxed_optimum(ir, {c.name: c.rhs + _FD_DELTA})
            prices[c.name] = None if bumped is None else (bumped - base) / _FD_DELTA
        except Exception:  # pragma: no cover
            prices[c.name] = None
    return prices


def _is_feasible(ir: LpIr, subset: list[Constraint]) -> bool:
    """Feasibility of the LP relaxation under a subset of constraints."""

    try:
        prob, _vars, _con = _build(ir, relax=True, subset=subset)
        # Drop the objective: we only care whether the feasible region is non-empty.
        prob.setObjective(pulp.lpSum([]))
        prob.solve(_solver())
        return prob.status == pulp.LpStatusOptimal
    except Exception:  # pragma: no cover
        return True


def _diagnose_infeasible(ir: LpIr) -> Diagnosis:
    """Deletion-filter IIS: a minimal subset of constraints that stays infeasible.

    Approximates an irreducible infeasible subset (Section 6.3). Operates on the
    LP relaxation for speed; variable bounds are always retained.
    """

    if not _is_feasible(ir, []):
        # Even with no row constraints the region is empty, so the variable
        # bounds themselves are contradictory.
        return Diagnosis(
            type="iis",
            constraints=[],
            detail="Infeasibility stems from variable bounds, not row constraints.",
        )

    current = list(ir.constraints)
    for c in list(ir.constraints):
        trial = [x for x in current if x is not c]
        if not _is_feasible(ir, trial):
            current = trial  # c was not essential to the infeasibility
    names = [c.name for c in current]
    return Diagnosis(
        type="iis",
        constraints=names,
        detail=(
            "These constraints are jointly infeasible; relaxing any one of them "
            "may restore feasibility."
        ),
    )


def _diagnose_unbounded(ir: LpIr) -> Diagnosis:
    """Identify variables driving the unbounded direction (Section 6.3)."""

    obj_coef = {t.var: t.coef for t in ir.objective}
    maximizing = ir.sense == "maximize"
    bounds = {v.name: (v.lower, v.upper) for v in ir.variables}

    ray: list[str] = []
    for var, coef in obj_coef.items():
        lower, upper = bounds.get(var, (None, None))
        improves_by_increasing = coef > 0 if maximizing else coef < 0
        improves_by_decreasing = coef < 0 if maximizing else coef > 0
        if improves_by_increasing and upper is None:
            ray.append(var)
        elif improves_by_decreasing and lower is None:
            ray.append(var)

    return Diagnosis(
        type="unbounded_ray",
        variables=ray,
        detail=(
            "Objective improves without bound along these variables; a limiting "
            "constraint or bound is missing."
        ),
    )
