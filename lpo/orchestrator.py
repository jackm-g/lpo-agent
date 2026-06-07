"""Orchestrator and recovery loop (Section 6.5).

Deterministic code owns control flow, the retry budget, the human-confirmation
gate, and the infeasible/unbounded recovery loop. The model only owns Formulate
and Explain.

The pipeline is written once as a generator that *pauses* (``yield``) when it
needs human approval. The synchronous :func:`run` drives it with a callback; the
REST API (two-call confirmation) resumes it across requests. One code path, two
front ends.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Generator, Optional, Union

from .config import Config, load_config
from .explanation import explain
from .formulation import formulate
from .models import (
    InfoResponse,
    LpIr,
    SolverResult,
    SuccessResponse,
)
from .observability import Trace
from .prompts import build_formulation_messages
from .providers import get_provider
from .providers.base import LlmProvider
from .solver import solve
from .validation import provenance_findings, restate, validate

Response = Union[SuccessResponse, InfoResponse]


@dataclass
class Session:
    """Carries one run's state across the (possibly multi-step) confirmation flow."""

    trace_id: str
    provider: LlmProvider
    messages: list[dict]
    question: str
    require_human_confirmation: bool
    max_retries: int
    config: Config
    trace: Trace
    gen: Optional[Generator] = None
    result: Optional[Response] = None
    pending_ir: Optional[LpIr] = None
    pending_restatement: Optional[str] = None


class Orchestrator:
    def __init__(self, config: Optional[Config] = None, provider: Optional[LlmProvider] = None):
        self.config = config or load_config()
        self._provider = provider  # injectable for tests (e.g. MockProvider)

    # ------------------------------------------------------------------ #
    # Synchronous entry point (CLI, tests)                                #
    # ------------------------------------------------------------------ #
    def run(
        self,
        question: str,
        context: Any = "",
        require_human_confirmation: bool = True,
        max_retries: int = 3,
        approve_fn: Optional[Callable[[str], bool]] = None,
    ) -> Response:
        """Run the full pipeline to completion.

        ``approve_fn(restatement) -> bool`` is consulted at each confirmation
        gate. If confirmation is required and no callback is supplied, the gate
        rejects (fail-closed).
        """

        session = self._new_session(
            question, context, require_human_confirmation, max_retries
        )
        gen = self._pipeline(session)
        session.gen = gen
        try:
            restatement = next(gen)
            while True:
                approved = approve_fn(restatement) if approve_fn else False
                restatement = gen.send(approved)
        except StopIteration:
            pass
        return session.result  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Two-call entry points (REST API)                                    #
    # ------------------------------------------------------------------ #
    def start(
        self,
        question: str,
        context: Any = "",
        require_human_confirmation: bool = True,
        max_retries: int = 3,
    ) -> tuple[Response, Optional[Session]]:
        """Advance until the first confirmation gate or completion.

        Returns (response, session). If the response is ``need_confirmation`` the
        session must be retained and later resumed via :meth:`approve`.
        """

        session = self._new_session(
            question, context, require_human_confirmation, max_retries
        )
        session.gen = self._pipeline(session)
        return self._drive(session, send_value=None)

    def approve(self, session: Session, approved: bool) -> tuple[Response, Optional[Session]]:
        """Resume a paused session with the human's decision."""

        return self._drive(session, send_value=approved)

    def _drive(self, session: Session, send_value) -> tuple[Response, Optional[Session]]:
        assert session.gen is not None
        try:
            if send_value is None:
                restatement = next(session.gen)
            else:
                restatement = session.gen.send(send_value)
        except StopIteration:
            return session.result, None  # type: ignore[return-value]

        # Paused at a confirmation gate.
        resp = InfoResponse(
            status="need_confirmation",
            message="Review the restatement and approve before solving.",
            trace_id=session.trace_id,
            ir=session.pending_ir,
            restatement=restatement,
        )
        return resp, session

    # ------------------------------------------------------------------ #
    # The pipeline (Section 6.5)                                          #
    # ------------------------------------------------------------------ #
    def _pipeline(self, session: Session) -> Generator[str, bool, None]:
        trace = session.trace
        for attempt in range(session.max_retries):
            outcome = formulate(session.provider, session.messages)

            if outcome.ir is None:
                # Schema-invalid or truncated; feed the error back (Section 6.2/8).
                trace.record_attempt(attempt=attempt, schema_errors=outcome.schema_errors,
                                     truncated=outcome.truncated)
                session.messages.append(
                    _correction_turn(
                        "Your previous output was not valid against the schema "
                        f"(truncated={outcome.truncated}): "
                        + "; ".join(outcome.schema_errors)
                    )
                )
                continue

            ir = outcome.ir
            session.messages.append(
                {"role": "assistant", "content": ir.model_dump_json()}
            )

            if ir.status == "need_info":
                trace.record_attempt(attempt=attempt, status="need_info",
                                     need_info=ir.need_info, reasoning=outcome.reasoning)
                session.result = self._finish(
                    session, "need_info", ir.need_info or "More information is needed."
                )
                return

            errors = validate(ir)
            trace.record_attempt(
                attempt=attempt,
                ir=ir.model_dump(),
                reasoning=outcome.reasoning,
                validation_errors=errors,
                provenance=[f.message for f in provenance_findings(ir)],
            )
            if errors:
                session.messages.append(
                    _correction_turn(
                        "The IR failed validation. Fix exactly these problems and "
                        "re-emit: " + "; ".join(errors)
                    )
                )
                continue

            restatement = restate(ir)
            session.pending_ir = ir
            session.pending_restatement = restatement
            trace.set(restatement=restatement)

            if session.require_human_confirmation:
                approved = yield restatement  # PAUSE for human approval
                trace.set(human_confirmation=approved)
                if not approved:
                    session.result = self._finish(
                        session, "need_info",
                        "Model rejected at the human confirmation gate.",
                    )
                    return
            else:
                trace.set(human_confirmation="bypassed")

            result: SolverResult = solve(ir)
            trace.set(solver_result=result.model_dump())

            if result.status == "optimal":
                ex = explain(
                    session.provider,
                    session.question,
                    result,
                    run_critic=session.config.enable_critic,
                )
                trace.set(
                    explanation=ex.text,
                    critic={"ok": ex.critic_ok, "issues": ex.critic_issues},
                )
                session.result = self._finish(
                    session, "optimal", "",
                    ir=ir, result=result, explanation=ex.text, restatement=restatement,
                )
                return

            # Infeasible or unbounded: feed the diagnosis back and reformulate.
            session.messages.append(_diagnosis_turn(result))

        # Retry budget exhausted (Section 6.5: the budget is mandatory).
        session.result = self._finish(
            session, "escalated",
            "Could not converge to a feasible, confirmed model within the retry budget.",
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #
    def _new_session(
        self, question, context, require_human_confirmation, max_retries
    ) -> Session:
        provider = self._provider or get_provider(self.config)
        trace_id = str(uuid.uuid4())
        return Session(
            trace_id=trace_id,
            provider=provider,
            messages=build_formulation_messages(question, context),
            question=question,
            require_human_confirmation=require_human_confirmation,
            max_retries=max_retries,
            config=self.config,
            trace=Trace(trace_id, question, context),
        )

    def _finish(
        self,
        session: Session,
        status: str,
        message: str,
        ir: Optional[LpIr] = None,
        result: Optional[SolverResult] = None,
        explanation: str = "",
        restatement: str = "",
    ) -> Response:
        session.trace.set(status=status)
        session.trace.flush()
        if status == "optimal":
            return SuccessResponse(
                ir=ir,  # type: ignore[arg-type]
                result=result,  # type: ignore[arg-type]
                explanation=explanation,
                restatement=restatement,
                trace_id=session.trace_id,
            )
        return InfoResponse(status=status, message=message, trace_id=session.trace_id)  # type: ignore[arg-type]


def _correction_turn(message: str) -> dict:
    return {"role": "user", "content": "VALIDATION FEEDBACK: " + message}


def _diagnosis_turn(result: SolverResult) -> dict:
    diag = result.diagnosis
    if result.status == "infeasible":
        detail = (
            f"The model is INFEASIBLE. An irreducible infeasible subset of "
            f"constraints is: {diag.constraints if diag else []}. "
            "Relax or correct one of these — e.g. a flipped inequality, a wrong "
            "RHS, or a missing degree of freedom — and re-formulate."
        )
    elif result.status == "unbounded":
        detail = (
            f"The model is UNBOUNDED along variables {diag.variables if diag else []}. "
            "A bounding constraint or variable upper/lower bound is missing. Add it "
            "and re-formulate."
        )
    else:
        detail = f"The solver reported '{result.status}': {result.error}. Re-formulate."
    return {"role": "user", "content": "SOLVER FEEDBACK: " + detail}
