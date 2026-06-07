"""Pydantic data models (Section 5).

The LP IR is the contract between the model and the solver. The JSON Schema fed
to the LLM provider is *generated* from these Pydantic models (see
``lp_ir_schema``) so code and schema never drift — there is one source of truth.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ``extra="forbid"`` makes every generated schema carry ``additionalProperties:
# false``, matching the spec and tightening provider-side constrained generation.
_STRICT = ConfigDict(extra="forbid")

VAR_NAME_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_]*$"


# --------------------------------------------------------------------------- #
# LP IR (Section 5.1)                                                          #
# --------------------------------------------------------------------------- #
class Variable(BaseModel):
    model_config = _STRICT

    name: str = Field(pattern=VAR_NAME_PATTERN)
    meaning: str
    lower: Optional[float]
    upper: Optional[float] = None
    integer: bool


class Term(BaseModel):
    """A ``coef * var`` term used in both the objective and constraints."""

    model_config = _STRICT

    var: str
    coef: float


class Constraint(BaseModel):
    model_config = _STRICT

    name: str
    terms: list[Term] = Field(min_length=1)
    op: Literal["<=", ">=", "=="]
    rhs: float
    source: str = Field(
        description="Verbatim or close paraphrase of the question span justifying "
        "this constraint."
    )


class LpIr(BaseModel):
    """Linear-program intermediate representation."""

    model_config = _STRICT

    status: Literal["formulated", "need_info"]
    need_info: Optional[str] = Field(
        default=None,
        description="Set only when status=need_info: the single most important "
        "clarifying question.",
    )
    sense: Literal["maximize", "minimize"]
    variables: list[Variable] = Field(min_length=1)
    objective: list[Term] = Field(min_length=1)
    # Required per the spec schema (Section 5.1) but may be an empty list, e.g.
    # an unconstrained model or a need_info stub.
    constraints: list[Constraint]


# --------------------------------------------------------------------------- #
# SolverResult (Section 5.2)                                                   #
# --------------------------------------------------------------------------- #
ShadowPriceBasis = Literal["lp", "lp_relaxation", "none"]


class ConstraintResult(BaseModel):
    model_config = _STRICT

    name: str
    lhs_value: float
    rhs: float
    binding: bool
    slack: float
    shadow_price: Optional[float] = None
    shadow_price_basis: ShadowPriceBasis = "none"


class Diagnosis(BaseModel):
    model_config = _STRICT

    type: Literal["iis", "unbounded_ray", "none"] = "none"
    constraints: list[str] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    detail: Optional[str] = None


class SolverResult(BaseModel):
    model_config = _STRICT

    status: Literal["optimal", "infeasible", "unbounded", "error"]
    is_integer_model: bool = False
    objective_value: Optional[float] = None
    variables: dict[str, float] = Field(default_factory=dict)
    constraints: list[ConstraintResult] = Field(default_factory=list)
    sensitivity: Optional[dict[str, Any]] = None
    diagnosis: Optional[Diagnosis] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# External API (Section 5.3)                                                   #
# --------------------------------------------------------------------------- #
class SolveRequest(BaseModel):
    question: str
    context: Any = ""  # string or structured object of known parameters/limits
    require_human_confirmation: bool = True
    max_retries: int = 3


class SuccessResponse(BaseModel):
    status: Literal["optimal"] = "optimal"
    ir: LpIr
    result: SolverResult
    explanation: str
    restatement: str
    trace_id: str


class InfoResponse(BaseModel):
    status: Literal["need_info", "escalated", "need_confirmation"]
    message: str
    trace_id: str
    # Populated for need_confirmation so the caller can review before approving.
    ir: Optional[LpIr] = None
    restatement: Optional[str] = None


# --------------------------------------------------------------------------- #
# Schema generation — single source of truth for providers (Section 6.6)       #
# --------------------------------------------------------------------------- #
def lp_ir_schema() -> dict[str, Any]:
    """JSON Schema for the LP IR, generated from the Pydantic model.

    Pydantic emits ``$defs``/``$ref``; we inline them because some provider
    structured-output surfaces dislike refs. The result is provider-neutral —
    each adapter translates it into its own structured-output mechanism.
    """

    schema = LpIr.model_json_schema()
    schema = _inline_refs(schema)
    schema["title"] = "LpIr"
    schema["$schema"] = "http://json-schema.org/draft-2020-12/schema"
    return schema


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = node["$ref"].split("/")[-1]
                target = resolve(defs[ref_name])
                # Merge sibling keys (e.g. description) over the resolved def.
                merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
                return merged
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)
