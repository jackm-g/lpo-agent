"""REST API tests — two-call confirmation flow (Sections 5.3, 15.3)."""

import json
import os

from fastapi.testclient import TestClient

from lpo import api
from lpo.config import Config
from lpo.orchestrator import Orchestrator
from lpo.providers.mock import MockProvider

HERE = os.path.dirname(__file__)
GOLDEN = json.load(open(os.path.join(HERE, "..", "goldens", "recon_resupply.json")))


def _client():
    cfg = Config(provider="mock", enable_critic=False)
    api._orchestrator = Orchestrator(config=cfg, provider=MockProvider(cfg))
    api._sessions.clear()
    return TestClient(api.app)


def test_single_call_when_no_confirmation():
    client = _client()
    r = client.post("/v1/solve", json={
        "question": GOLDEN["question"], "require_human_confirmation": False})
    body = r.json()
    assert body["status"] == "optimal"
    assert body["result"]["objective_value"] == 36.0


def test_two_call_confirmation_then_approve():
    client = _client()
    r1 = client.post("/v1/solve", json={
        "question": GOLDEN["question"], "require_human_confirmation": True})
    b1 = r1.json()
    assert b1["status"] == "need_confirmation"
    assert b1["restatement"]
    trace_id = b1["trace_id"]

    r2 = client.post("/v1/confirm", json={"trace_id": trace_id, "approved": True})
    b2 = r2.json()
    assert b2["status"] == "optimal"
    assert b2["result"]["variables"] == {"x1": 2.0, "x2": 6.0}


def test_two_call_confirmation_then_reject():
    client = _client()
    b1 = client.post("/v1/solve", json={
        "question": GOLDEN["question"], "require_human_confirmation": True}).json()
    b2 = client.post("/v1/confirm",
                     json={"trace_id": b1["trace_id"], "approved": False}).json()
    assert b2["status"] == "need_info"


def test_confirm_unknown_trace_id_404():
    client = _client()
    r = client.post("/v1/confirm", json={"trace_id": "nope", "approved": True})
    assert r.status_code == 404


def test_healthz():
    client = _client()
    assert client.get("/healthz").json()["status"] == "ok"
