"""End-to-end orchestrator tests with the mock provider (Sections 6.5, 11)."""

import copy
import json
import os

from lpo.config import Config
from lpo.eval import (
    grounded_numbers,
    ir_equivalent,
    ir_signature,
    solution_satisfies_constraints,
)
from lpo.explanation import _NUMBER_RE
from lpo.models import InfoResponse, LpIr, SuccessResponse
from lpo.orchestrator import Orchestrator
from lpo.providers.mock import MockProvider

HERE = os.path.dirname(__file__)
GOLDEN = json.load(open(os.path.join(HERE, "..", "goldens", "recon_resupply.json")))


def _orch(scripted=None):
    cfg = Config(provider="mock", enable_critic=True)
    return Orchestrator(config=cfg, provider=MockProvider(cfg, scripted_irs=scripted))


def test_golden_recon_ir_equivalence_and_solution():
    orch = _orch()
    resp = orch.run(GOLDEN["question"], require_human_confirmation=False)
    assert isinstance(resp, SuccessResponse)

    expected = LpIr.model_validate(GOLDEN["expected_ir"])
    assert ir_equivalent(resp.ir, expected)

    # Solver correctness by re-substitution (Section 11).
    assert solution_satisfies_constraints(resp.ir, resp.result) == []
    assert resp.result.objective_value == GOLDEN["expected_solution"]["objective_value"]


def test_explanation_is_faithful():
    orch = _orch()
    resp = orch.run(GOLDEN["question"], require_human_confirmation=False)
    grounded = grounded_numbers(resp.result)
    for token in _NUMBER_RE.findall(resp.explanation):
        norm = str(int(float(token))) if float(token) == int(float(token)) else token
        assert norm in grounded, f"ungrounded number {token!r} in explanation"


def test_ir_equivalence_is_name_invariant():
    a = LpIr.model_validate(GOLDEN["expected_ir"])
    renamed = copy.deepcopy(GOLDEN["expected_ir"])
    # Rename x1->recon everywhere; signatures should still match.
    for v in renamed["variables"]:
        if v["name"] == "x1":
            v["name"] = "recon"
    for t in renamed["objective"]:
        if t["var"] == "x1":
            t["var"] = "recon"
    for c in renamed["constraints"]:
        for t in c["terms"]:
            if t["var"] == "x1":
                t["var"] = "recon"
    b = LpIr.model_validate(renamed)
    assert ir_signature(a) == ir_signature(b)


def test_need_info_short_circuits():
    orch = _orch()
    resp = orch.run("How many chairs and tables should we build to maximize profit?",
                    require_human_confirmation=False)
    assert isinstance(resp, InfoResponse)
    assert resp.status == "need_info"


def test_confirmation_gate_rejection():
    orch = _orch()
    resp = orch.run(GOLDEN["question"], require_human_confirmation=True,
                    approve_fn=lambda _r: False)
    assert isinstance(resp, InfoResponse)
    assert resp.status == "need_info"
    assert "confirmation gate" in resp.message


def test_recovery_loop_reformulates_after_infeasible():
    # First IR is infeasible (x>=10 and x<=5); second is the good recon IR.
    infeasible = {
        "status": "formulated", "sense": "maximize",
        "variables": [{"name": "x", "meaning": "x", "lower": 0, "integer": False}],
        "objective": [{"var": "x", "coef": 1}],
        "constraints": [
            {"name": "hi", "terms": [{"var": "x", "coef": 1}], "op": ">=", "rhs": 10, "source": "a"},
            {"name": "lo", "terms": [{"var": "x", "coef": 1}], "op": "<=", "rhs": 5, "source": "b"},
        ],
    }
    orch = _orch(scripted=[infeasible, copy.deepcopy(GOLDEN["expected_ir"])])
    resp = orch.run(GOLDEN["question"], require_human_confirmation=False, max_retries=3)
    assert isinstance(resp, SuccessResponse)
    assert resp.result.objective_value == 36.0


def test_retry_budget_escalates():
    infeasible = {
        "status": "formulated", "sense": "maximize",
        "variables": [{"name": "x", "meaning": "x", "lower": 0, "integer": False}],
        "objective": [{"var": "x", "coef": 1}],
        "constraints": [
            {"name": "hi", "terms": [{"var": "x", "coef": 1}], "op": ">=", "rhs": 10, "source": "a"},
            {"name": "lo", "terms": [{"var": "x", "coef": 1}], "op": "<=", "rhs": 5, "source": "b"},
        ],
    }
    orch = _orch(scripted=[copy.deepcopy(infeasible) for _ in range(3)])
    resp = orch.run("q", require_human_confirmation=False, max_retries=3)
    assert isinstance(resp, InfoResponse)
    assert resp.status == "escalated"
