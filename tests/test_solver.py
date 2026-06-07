"""Solver tests (Sections 6.3, 7.3, 7.4)."""

import copy

import pytest

from lpo.eval import solution_satisfies_constraints
from lpo.models import LpIr
from lpo.providers.mock import RECON_IR
from lpo.solver import solve


def _ir(d):
    return LpIr.model_validate(copy.deepcopy(d))


def test_recon_optimum_matches_spec():
    r = solve(_ir(RECON_IR))
    assert r.status == "optimal"
    assert r.is_integer_model is True
    assert r.objective_value == 36.0
    assert r.variables == {"x1": 2.0, "x2": 6.0}


def test_recon_binding_and_shadow_prices():
    r = solve(_ir(RECON_IR))
    by_name = {c.name: c for c in r.constraints}
    assert by_name["fuel"].binding and by_name["aircrew"].binding
    assert not by_name["airframes"].binding
    assert by_name["fuel"].shadow_price == pytest.approx(1.5)
    assert by_name["aircrew"].shadow_price == pytest.approx(1.0)
    assert by_name["airframes"].shadow_price == pytest.approx(0.0)
    # Integer model -> relaxation basis label (Section 7.3).
    assert by_name["fuel"].shadow_price_basis == "lp_relaxation"


def test_returned_solution_is_feasible():
    r = solve(_ir(RECON_IR))
    assert solution_satisfies_constraints(_ir(RECON_IR), r) == []


def test_continuous_model_uses_lp_basis():
    cont = copy.deepcopy(RECON_IR)
    for v in cont["variables"]:
        v["integer"] = False
    r = solve(_ir(cont))
    assert r.is_integer_model is False
    fuel = next(c for c in r.constraints if c.name == "fuel")
    assert fuel.shadow_price_basis == "lp"


def test_infeasible_produces_iis():
    d = {
        "status": "formulated", "sense": "maximize",
        "variables": [{"name": "x", "meaning": "x", "lower": 0, "integer": False}],
        "objective": [{"var": "x", "coef": 1}],
        "constraints": [
            {"name": "hi", "terms": [{"var": "x", "coef": 1}], "op": ">=", "rhs": 10, "source": "a"},
            {"name": "lo", "terms": [{"var": "x", "coef": 1}], "op": "<=", "rhs": 5, "source": "b"},
        ],
    }
    r = solve(_ir(d))
    assert r.status == "infeasible"
    assert set(r.diagnosis.constraints) == {"hi", "lo"}


def test_unbounded_produces_ray():
    d = {
        "status": "formulated", "sense": "maximize",
        "variables": [{"name": "x", "meaning": "x", "lower": 0, "upper": None, "integer": False}],
        "objective": [{"var": "x", "coef": 1}],
        "constraints": [],
    }
    r = solve(_ir(d))
    assert r.status == "unbounded"
    assert "x" in r.diagnosis.variables
