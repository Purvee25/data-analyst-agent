"""Tests for the free local-LLM adapter (analyst/ollama_client.py).

The adapter's whole job is to be shaped exactly like the Anthropic client so the
insight/critic/Q&A agents run unchanged. These tests pin that contract without a
running Ollama server by stubbing the HTTP call:
  * the returned object exposes `.stop_reason` and `.content[i].text`
  * a JSON schema is forwarded to Ollama as the `format` field
  * a network failure raises OllamaError, which subclasses OSError so the shared
    llm_json helper catches it in the same net as an anthropic APIError
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from analyst.ollama_client import OllamaClient, OllamaError


class _FakeResponse(io.BytesIO):
    """Context-manager byte stream mimicking urlopen's return value."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, capture: dict, *, content='{"ok": true}'):
    def fake_urlopen(req, timeout=None):
        capture["payload"] = json.loads(req.data.decode("utf-8"))
        capture["timeout"] = timeout
        body = json.dumps({"message": {"role": "assistant", "content": content}})
        return _FakeResponse(body.encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


def test_response_has_anthropic_shape(monkeypatch):
    cap: dict = {}
    _patch_urlopen(monkeypatch, cap, content='{"insights": []}')
    client = OllamaClient(model="test-model")

    resp = client.messages.create(
        model="claude-opus-4-8",  # ignored in favour of the configured local model
        max_tokens=500,
        system="You are a test.",
        messages=[{"role": "user", "content": "hi"}],
    )

    # Shape llm_json._extract_text depends on.
    assert resp.stop_reason == "end_turn"
    assert resp.content[0].type == "text"
    assert resp.content[0].text == '{"insights": []}'
    # System prompt is prepended as a system message; the local model is used.
    assert cap["payload"]["model"] == "test-model"
    assert cap["payload"]["messages"][0] == {"role": "system", "content": "You are a test."}


def test_schema_forwarded_as_format(monkeypatch):
    cap: dict = {}
    _patch_urlopen(monkeypatch, cap)
    client = OllamaClient(model="test-model")

    schema = {"type": "object", "properties": {"x": {"type": "number"}}}
    client.messages.create(
        model="ignored",
        max_tokens=100,
        system="s",
        messages=[{"role": "user", "content": "q"}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )

    # Ollama constrains output when handed the schema on `format`.
    assert cap["payload"]["format"] == schema


def test_network_failure_raises_ollama_error_subclassing_oserror(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    client = OllamaClient(model="test-model")

    with pytest.raises(OllamaError) as exc:
        client.messages.create(
            model="ignored", max_tokens=100, system="s",
            messages=[{"role": "user", "content": "q"}],
        )
    # Must be catchable as OSError (that's how llm_json wraps provider errors).
    assert isinstance(exc.value, OSError)
