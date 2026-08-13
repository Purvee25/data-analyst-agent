"""Tests for the free hosted Groq adapter (analyst/groq_client.py).

Same contract as the Ollama adapter — Anthropic-shaped responses — but over
Groq's OpenAI-compatible HTTP API. The network call is stubbed so no key or
connection is needed.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from analyst.groq_client import GroqClient, GroqError


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch(monkeypatch, capture: dict, *, content='{"ok": true}'):
    def fake_urlopen(req, timeout=None):
        capture["url"] = req.full_url
        capture["headers"] = {k.lower(): v for k, v in req.headers.items()}
        capture["payload"] = json.loads(req.data.decode("utf-8"))
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]})
        return _FakeResponse(body.encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


def test_missing_key_raises_groq_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(GroqError, match="GROQ_API_KEY"):
        GroqClient()


def test_response_has_anthropic_shape_and_auth(monkeypatch):
    cap: dict = {}
    _patch(monkeypatch, cap, content='{"insights": []}')
    client = GroqClient(api_key="gsk-test", model="test-model")

    resp = client.messages.create(
        model="claude-opus-4-8",  # ignored
        max_tokens=500,
        system="You are a test.",
        messages=[{"role": "user", "content": "hi"}],
        output_config={"format": {"type": "json_schema", "schema": {}}},
    )

    assert resp.stop_reason == "end_turn"
    assert resp.content[0].text == '{"insights": []}'
    # OpenAI-shaped payload: system prepended, JSON mode on, bearer auth set.
    assert cap["payload"]["messages"][0] == {"role": "system", "content": "You are a test."}
    assert cap["payload"]["response_format"] == {"type": "json_object"}
    assert cap["headers"]["authorization"] == "Bearer gsk-test"


def test_http_error_becomes_groq_error(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))

    monkeypatch.setattr("urllib.request.urlopen", boom)
    client = GroqClient(api_key="gsk-test", model="m")
    with pytest.raises(GroqError) as exc:
        client.messages.create(model="x", max_tokens=10, system="s", messages=[{"role": "user", "content": "q"}])
    assert isinstance(exc.value, OSError)
