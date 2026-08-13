"""HTTP-contract tests for the FastAPI layer (api/main.py).

These exercise the endpoints that don't require a live LLM — the load-bearing
paths that were previously only tested indirectly: health/provider reporting,
metrics aggregation, rate limiting, session errors, cleaning, and the
human-confirmed email action (with the MCP send stubbed). LLM calls are never
made: insight/ask rate-limit tests trip the limiter *before* any model call, and
the email test stubs the executor.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from analyst import actions, config, logger
from api import main as api_main

client = TestClient(api_main.app)


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Each test starts with an empty server-side session store."""
    api_main._SESSIONS.clear()
    yield
    api_main._SESSIONS.clear()


def _load_demo() -> str:
    resp = client.post("/api/session/demo")
    assert resp.status_code == 200
    return resp.json()["session_id"]


# --- health ---------------------------------------------------------------
def test_health_reports_ollama_provider(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["provider"] == "ollama"
    assert body["is_local"] is True
    assert body["ready"] is True  # local needs no API key


def test_health_groq_ready_depends_on_groq_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.delenv(config.GROQ_API_KEY_ENV, raising=False)
    body = client.get("/api/health").json()
    assert body["provider"] == "groq"
    assert body["is_free"] is True
    assert body["is_local"] is False
    assert body["ready"] is False  # no key yet

    monkeypatch.setenv(config.GROQ_API_KEY_ENV, "gsk-test")
    assert client.get("/api/health").json()["ready"] is True


def test_health_not_ready_when_claude_without_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.delenv(config.API_KEY_ENV_VAR, raising=False)
    body = client.get("/api/health").json()
    assert body["is_local"] is False
    assert body["ready"] is False


# --- demo / cleaning ------------------------------------------------------
def test_demo_load_returns_cleaned_payload():
    body = client.post("/api/session/demo").json()
    assert body["rows"] > 0 and body["cols"] > 0
    assert "quality" in body and "preview" in body
    assert body["requests_used"] == 0
    assert body["requests_max"] == config.MAX_REQUESTS_PER_SESSION


# --- metrics --------------------------------------------------------------
def test_metrics_empty_when_no_log(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOG_CSV_PATH", str(tmp_path / "none.csv"))
    body = client.get("/api/metrics").json()
    assert body["total"] == 0
    assert body["confidence_series"] == []


def test_metrics_aggregates_logged_rows(monkeypatch, tmp_path):
    log_path = tmp_path / "requests.csv"
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LOG_CSV_PATH", str(log_path))
    logger.log_request("generate_insights", "ok", success=True, response_time_seconds=1.2, confidence_score=0.8)
    logger.log_request("generate_insights", "ok", success=False, response_time_seconds=0.4)

    body = client.get("/api/metrics").json()
    assert body["total"] == 2
    assert body["success_rate"] == 50.0
    assert body["avg_confidence"] == 0.8  # only the one row with a score
    assert body["confidence_series"] == [0.8]


# --- session + rate limiting ---------------------------------------------
def test_insights_unknown_session_404():
    resp = client.post("/api/insights", json={"session_id": "does-not-exist"})
    assert resp.status_code == 404


def test_insights_rate_limited_before_any_model_call():
    sid = _load_demo()
    api_main._SESSIONS[sid].request_count = config.MAX_REQUESTS_PER_SESSION
    resp = client.post("/api/insights", json={"session_id": sid})
    assert resp.status_code == 429
    assert "limit" in resp.json()["detail"].lower()


def test_ask_rejects_destructive_question():
    sid = _load_demo()
    resp = client.post("/api/ask", json={"session_id": sid, "question": "DROP TABLE sales;"})
    assert resp.status_code == 400


# --- email action (MCP send stubbed) -------------------------------------
_INSIGHT = {
    "insight": "West region drives 45% of profit.",
    "supporting_data": "profit_by_region West=0.45",
    "category": "comparison",
    "confidence": 0.82,
    "critic_verdict": "approve",
    "critic_reasoning": "Backed by the aggregate.",
}


def test_email_action_success(monkeypatch):
    sid = _load_demo()
    monkeypatch.setattr(actions, "execute_action", lambda spec: "Email sent to ops@example.com")
    resp = client.post("/api/action/email", json={"session_id": sid, "insight": _INSIGHT})
    assert resp.status_code == 200
    assert resp.json()["actions_used"] == 1


def test_email_action_send_failure_is_502(monkeypatch):
    sid = _load_demo()

    def boom(spec):
        raise actions.ActionError("missing SMTP env var")

    monkeypatch.setattr(actions, "execute_action", boom)
    resp = client.post("/api/action/email", json={"session_id": sid, "insight": _INSIGHT})
    assert resp.status_code == 502
    assert "Could not send email" in resp.json()["detail"]


def test_email_action_rate_limited():
    sid = _load_demo()
    api_main._SESSIONS[sid].action_count = config.MAX_ACTIONS_PER_SESSION
    resp = client.post("/api/action/email", json={"session_id": sid, "insight": _INSIGHT})
    assert resp.status_code == 429
