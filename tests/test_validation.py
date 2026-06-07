"""Validation layer tests (Section 6.2)."""

import copy

from lpo.models import LpIr
from lpo.providers.mock import RECON_IR
from lpo.validation import coerce_ir, restate, validate


def _ir():
    return LpIr.model_validate(copy.deepcopy(RECON_IR))


def test_valid_ir_passes():
    assert validate(_ir()) == []


def test_dangling_variable_reference_in_objective():
    ir = _ir()
    ir.objective[0].var = "ghost"
    errors = validate(ir)
    assert any("undeclared variable 'ghost'" in e for e in errors)


def test_dangling_variable_reference_in_constraint():
    ir = _ir()
    ir.constraints[0].terms[0].var = "ghost"
    errors = validate(ir)
    assert any("ghost" in e for e in errors)


def test_duplicate_variable_names():
    ir = _ir()
    ir.variables[1].name = ir.variables[0].name
    errors = validate(ir)
    assert any("Duplicate variable name" in e for e in errors)


def test_duplicate_constraint_names():
    ir = _ir()
    ir.constraints[1].name = ir.constraints[0].name
    errors = validate(ir)
    assert any("Duplicate constraint name" in e for e in errors)


def test_inverted_bounds():
    ir = _ir()
    ir.variables[0].lower = 10
    ir.variables[0].upper = 1
    errors = validate(ir)
    assert any("lower=10" in e for e in errors)


def test_repeated_variable_in_one_constraint_flagged():
    ir = _ir()
    # Two terms on the same variable in one constraint -> aggregation/nonlinearity smell.
    ir.constraints[0].terms.append(ir.constraints[0].terms[0].model_copy())
    errors = validate(ir)
    assert any("more than once" in e for e in errors)


def test_coerce_rejects_bad_schema():
    ir, errors = coerce_ir({"status": "formulated"})  # missing required fields
    assert ir is None
    assert errors


def test_restatement_mentions_sense_and_sources():
    text = restate(_ir())
    assert "maximize" in text
    assert "because:" in text  # provenance is rendered into the restatement
