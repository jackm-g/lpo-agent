"""Explanation service (Section 6.4). Narrates a SolverResult — no new numbers.

Every number in the explanation must originate in the SolverResult (Section 7.4),
so the prompt embeds the result verbatim under a ``SOLVER_RESULT_JSON:`` marker
and instructs the model to paraphrase, not compute. An optional critic pass
(Section 6.4) checks the narrative against the result before it ships.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .models import SolverResult
from .prompts import CRITIC_SYSTEM_PROMPT, EXPLANATION_SYSTEM_PROMPT
from .providers.base import LlmProvider


@dataclass
class ExplanationOutcome:
    text: str
    critic_ok: bool = True
    critic_issues: list[str] = field(default_factory=list)


def explain(
    provider: LlmProvider,
    question: str,
    result: SolverResult,
    run_critic: bool = True,
) -> ExplanationOutcome:
    result_json = result.model_dump_json(indent=2)
    messages = [
        {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Original question:\n{question}\n\n"
                "Explain the result below to the decision-maker. Use only numbers "
                "that appear in it.\n\n"
                f"SOLVER_RESULT_JSON:\n{result_json}"
            ),
        },
    ]
    text = provider.explain(messages)

    if not run_critic:
        return ExplanationOutcome(text=text)

    ok, issues = _critic(provider, result, text)
    return ExplanationOutcome(text=text, critic_ok=ok, critic_issues=issues)


def _critic(
    provider: LlmProvider, result: SolverResult, explanation: str
) -> tuple[bool, list[str]]:
    """Second cheap pass: flag contradictions with the SolverResult.

    Combines a model judgment with a deterministic check that every number in
    the prose actually appears in the result — cheaper than shipping a wrong
    narrative, and the deterministic half works even with the mock provider.
    """

    issues = _ungrounded_numbers(result, explanation)

    messages = [
        {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"SOLVER_RESULT_JSON:\n{result.model_dump_json(indent=2)}\n\n"
                f"Proposed explanation:\n{explanation}"
            ),
        },
    ]
    try:
        verdict = provider.explain(messages)
        parsed = json.loads(_first_json_object(verdict))
        if parsed.get("ok") is False:
            issues.extend(parsed.get("issues", []) or ["critic flagged the explanation"])
    except Exception:
        # A non-JSON critic reply is not itself a failure; rely on the
        # deterministic number check above.
        pass

    return (len(issues) == 0), issues


# --------------------------------------------------------------------------- #
# Deterministic faithfulness check (also reused by the eval, Section 11)        #
# --------------------------------------------------------------------------- #
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def grounded_numbers(result: SolverResult) -> set[str]:
    """Every numeric value present in the SolverResult, normalized to strings."""

    grounded: set[str] = set()

    def add(x) -> None:
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            grounded.add(_norm(float(x)))

    add(result.objective_value)
    for v in result.variables.values():
        add(v)
    for c in result.constraints:
        add(c.lhs_value)
        add(c.rhs)
        add(c.slack)
        add(c.shadow_price)
    return grounded


def _ungrounded_numbers(result: SolverResult, explanation: str) -> list[str]:
    grounded = grounded_numbers(result)
    issues: list[str] = []
    for token in _NUMBER_RE.findall(explanation):
        if _norm(float(token)) not in grounded:
            issues.append(
                f"Explanation cites '{token}', which is not in the SolverResult."
            )
    return issues


def _norm(x: float) -> str:
    # Normalize so 2 == 2.0 == 2.00 compare equal.
    if x == int(x):
        return str(int(x))
    return f"{x:.6f}".rstrip("0")


def _first_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return text[start : end + 1]
