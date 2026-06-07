"""REST API (Section 5.3).

Two-call confirmation pattern (Section 15.3, the simpler option to operate
behind REST): ``POST /v1/solve`` formulates and, if confirmation is required,
returns a restatement plus a ``trace_id``; ``POST /v1/confirm`` approves (or
rejects) and continues to the solved, explained result. When
``require_human_confirmation`` is false, ``/v1/solve`` returns the final result
in one call.

In-memory session store — single-process deployment. Front a horizontally-scaled
deployment with sticky sessions or an external store.
"""

from __future__ import annotations

from typing import Optional, Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .models import InfoResponse, SolveRequest, SuccessResponse
from .orchestrator import Orchestrator, Session

app = FastAPI(title="LPO Agent", version="0.2.0")

_orchestrator = Orchestrator()
_sessions: dict[str, Session] = {}


class ConfirmRequest(BaseModel):
    trace_id: str
    approved: bool


def _store_if_pending(resp, session: Optional[Session]) -> None:
    if session is not None and getattr(resp, "status", None) == "need_confirmation":
        _sessions[session.trace_id] = session
    elif session is None:
        # Terminal — nothing to retain.
        pass


@app.post("/v1/solve", response_model=Union[SuccessResponse, InfoResponse])
def solve_endpoint(req: SolveRequest):
    resp, session = _orchestrator.start(
        question=req.question,
        context=req.context,
        require_human_confirmation=req.require_human_confirmation,
        max_retries=req.max_retries,
    )
    _store_if_pending(resp, session)
    return resp


@app.post("/v1/confirm", response_model=Union[SuccessResponse, InfoResponse])
def confirm_endpoint(req: ConfirmRequest):
    session = _sessions.pop(req.trace_id, None)
    if session is None:
        raise HTTPException(404, f"No pending session for trace_id {req.trace_id}.")
    resp, session2 = _orchestrator.approve(session, req.approved)
    _store_if_pending(resp, session2)
    return resp


@app.get("/healthz")
def healthz():
    return {"status": "ok", "provider": _orchestrator.config.provider}
