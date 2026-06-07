"""System prompts and few-shot examples (Sections 6.1, 6.4).

The static prefix here (system instructions + schema + few-shot) is identical on
every request, so it is the natural prompt-cache target (Section 3.2).
"""

from __future__ import annotations

import json
from typing import Any

from .models import lp_ir_schema

# --------------------------------------------------------------------------- #
# Few-shot examples                                                            #
# --------------------------------------------------------------------------- #
# 1) Worked recon/resupply instance (implicit non-negativity via lower=0).
_FEWSHOT_RECON_Q = (
    "We have 4 ISR airframe-days. Recon uses one airframe each. Resupply burns 2 "
    "fuel pallets each and we have 12 pallets. Aircrew duty hours total 18; recon "
    "needs 3 hours, resupply 2. Each recon sortie is worth 3, each resupply 5. "
    "How many of each should we fly to maximize value?"
)
_FEWSHOT_RECON_A = {
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

# 2) Deliberately underspecified — the correct output is need_info, not a guess.
_FEWSHOT_NEEDINFO_Q = "We make chairs and tables. How many should we build to maximize profit?"
_FEWSHOT_NEEDINFO_A = {
    "status": "need_info",
    "need_info": "What is the per-unit profit of a chair and a table, and what "
    "resource limits (labor, materials, machine time) constrain production?",
    "sense": "maximize",
    "variables": [{"name": "chairs", "meaning": "chairs to build", "lower": 0, "integer": True}],
    "objective": [{"var": "chairs", "coef": 1}],
    "constraints": [],
}


def _example_turn(question: str, answer: dict[str, Any]) -> list[dict]:
    return [
        {"role": "user", "content": question},
        {"role": "assistant", "content": json.dumps(answer)},
    ]


def formulation_system_prompt() -> str:
    schema = json.dumps(lp_ir_schema(), indent=2)
    return f"""You convert a natural-language decision question into a formal \
linear (or mixed-integer linear) program. You NEVER solve it — a deterministic \
solver does that. Your only job is to emit the LP intermediate representation \
(LP IR) as JSON.

You must obey the following JSON Schema exactly. The generation is \
schema-constrained, so structurally invalid output is impossible; your \
responsibility is SEMANTIC correctness.

LP IR JSON Schema:
{schema}

Hard rules:
- Every constraint MUST carry a `source`: the verbatim or closely paraphrased \
span of the question that justifies it. Never invent a constraint you cannot \
cite.
- If a number you need is absent from the question/context, do NOT invent it. \
Return status="need_info" with the single most important clarifying question.
- If the relationship implied is nonlinear (a product of two variables, \
economies of scale, if-then/either-or logic), do NOT linearize silently. Return \
status="need_info" explaining what is nonlinear.
- Encode implicit constraints that are physically obvious (e.g. quantities are \
non-negative via lower=0), but only those that clearly follow.
- temperature is 0: be deterministic. Do not vary coefficients creatively.
- Choose the objective `sense` deliberately; a flipped sense is a serious error."""


def build_formulation_messages(question: str, context: Any) -> list[dict]:
    """System + few-shot + the user's question (Section 6.5 build_initial_messages)."""

    context_str = (
        context if isinstance(context, str) else json.dumps(context, indent=2)
    )
    user_block = f"Question:\n{question}"
    if context_str and context_str.strip() not in ("", "{}", "null"):
        user_block += f"\n\nContext (known parameters and limits):\n{context_str}"

    messages = [{"role": "system", "content": formulation_system_prompt()}]
    messages += _example_turn(_FEWSHOT_RECON_Q, _FEWSHOT_RECON_A)
    messages += _example_turn(_FEWSHOT_NEEDINFO_Q, _FEWSHOT_NEEDINFO_A)
    messages.append({"role": "user", "content": user_block})
    return messages


# --------------------------------------------------------------------------- #
# Explanation prompts (Section 6.4)                                            #
# --------------------------------------------------------------------------- #
EXPLANATION_SYSTEM_PROMPT = """You explain the result of a solved optimization \
to a decision-maker in plain language. You do NO arithmetic and introduce NO new \
numbers: every number in your explanation must already appear in the provided \
SolverResult. Cover:
- The decision (the variable values) in the user's terms.
- Which constraints are binding (the bottlenecks) and which have slack.
- Shadow prices for binding constraints. If shadow_price_basis is \
"lp_relaxation", you MUST say these are relaxation-based directional indicators, \
not exact marginal values for the integer problem.
- The honest limit on any "one more unit is worth X" claim.
Be concise and concrete."""

CRITIC_SYSTEM_PROMPT = """You are a fact-checker. You are given a SolverResult \
(ground truth) and a proposed explanation. Find any statement that contradicts \
the SolverResult: a number not present in it, a slack constraint called binding \
(or vice-versa), a wrong objective value, or an integer shadow price stated as \
exact. Respond with a JSON object: {"ok": true} if the explanation is faithful, \
or {"ok": false, "issues": ["..."]} listing each problem."""
