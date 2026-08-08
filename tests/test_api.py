"""Endpoint tests for the FastAPI app (api/main.py).

Focus on the surfaces added for feature-parity — health honesty, the metrics
aggregation, and the human-confirmed email action — plus the rate-limit and
session guards. All external effects (the MCP email send) are injected/faked so
no test spawns a subprocess or touches SMTP.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import main


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def session_id(client):
    """A real cleaned session via the demo endpoint (no LLM calls involved)."""
    resp = client.post("/api/session/demo")
    assert resp.status_code == 200
    return resp.json()["session_id"]


def _insight() -> dict:
    return {
        "insight": "Sales peak in Q4.",
        "supporting_data": "Q4 avg 2x Q1.",
        "category": "trend",
        "confidence": 0.82,
        "critic_verdict": "approve",
        "critic_reasoning": "Consistent across years.",
    }


# --- health ---------------------------------------------------------------
def test_health_reports_provider_and_email_flag(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "provider" in body and "is_local" in body
    assert "email_configured" in body  # UI relies on this to gate the button


# --- metrics --------------------------------------------------------------
def test_metrics_shape_never_500s(client, tmp_path, monkeypatch):
    # Point the log at an empty temp path: metrics must degrade to zeros, not error.
    monkeypatch.setattr(main.config, "LOG_CSV_PATH", str(tmp_path / "nope.csv"))
    body = client.get("/api/metrics").json()
    assert body["total"] == 0
    assert body["confidence_series"] == []


def test_metrics_aggregates_a_log(client, tmp_path, monkeypatch):
    log = tmp_path / "requests.csv"
    pd.DataFrame(
        {
            "timestamp": ["t1", "t2"],
            "action": ["generate_insights", "generate_insights"],
            "detail": ["ok", "ok"],
            "success": [True, False],
            "response_time_seconds": [1.0, 3.0],
            "confidence_score": [0.8, 0.6],
        }
    ).to_csv(log, index=False)
    monkeypatch.setattr(main.config, "LOG_CSV_PATH", str(log))

    body = client.get("/api/metrics").json()
    assert body["total"] == 2
    assert body["success_rate"] == 50.0
    assert body["avg_latency"] == 2.0
    assert body["avg_confidence"] == 0.7
    assert body["confidence_series"] == [0.8, 0.6]


# --- email action ---------------------------------------------------------
def test_email_action_success_uses_injected_send(client, session_id, monkeypatch):
    sent: dict = {}

    def fake_execute(spec):
        sent["spec"] = spec
        return "Email sent to ops@example.com"

    monkeypatch.setattr(main.actions, "execute_action", fake_execute)

    resp = client.post("/api/action/email", json={"session_id": session_id, "insight": _insight()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["actions_used"] == 1
    assert "sent" in body["result"].lower()
    # The server built the spec from the insight (never trusted a client subject).
    assert sent["spec"]["action"] == "email_alert"


def test_email_action_unknown_session_404s(client):
    resp = client.post("/api/action/email", json={"session_id": "nope", "insight": _insight()})
    assert resp.status_code == 404


def test_email_action_send_failure_is_clean_502(client, session_id, monkeypatch):
    def boom(spec):
        raise main.actions.ActionError("Missing required SMTP env var(s): SMTP_HOST.")

    monkeypatch.setattr(main.actions, "execute_action", boom)
    resp = client.post("/api/action/email", json={"session_id": session_id, "insight": _insight()})
    assert resp.status_code == 502
    assert "SMTP" in resp.json()["detail"]


def test_email_action_respects_session_limit(client, session_id, monkeypatch):
    monkeypatch.setattr(main.actions, "execute_action", lambda spec: "sent")
    monkeypatch.setattr(main.config, "MAX_ACTIONS_PER_SESSION", 1)

    ok = client.post("/api/action/email", json={"session_id": session_id, "insight": _insight()})
    assert ok.status_code == 200
    blocked = client.post("/api/action/email", json={"session_id": session_id, "insight": _insight()})
    assert blocked.status_code == 429
