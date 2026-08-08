"""Unit tests for the shared schema-constrained-call helper (retry/refusal paths)."""

from __future__ import annotations

import pytest

from analyst.llm_json import ClaudeJSONError, call_for_json
from tests.conftest import FakeClient, text_response

ARGS = dict(model="claude-test", max_tokens=100, system="sys", user_content="hi", schema={"type": "object"})


def test_valid_json_first_try():
    client = FakeClient(responses=[text_response({"ok": True})])
    assert call_for_json(client, **ARGS) == {"ok": True}
    assert len(client.messages.calls) == 1


def test_malformed_json_retries_once_with_clarification():
    client = FakeClient(responses=[text_response("not json {"), text_response({"ok": 1})])
    assert call_for_json(client, **ARGS) == {"ok": 1}
    assert len(client.messages.calls) == 2
    assert "could not be parsed" in client.messages.calls[1]["messages"][-1]["content"]


def test_malformed_twice_gives_up_with_clean_error():
    client = FakeClient(responses=[text_response("junk"), text_response("junk")])
    with pytest.raises(ClaudeJSONError, match="malformed JSON twice"):
        call_for_json(client, **ARGS)


def test_refusal_surfaces_as_clean_error():
    client = FakeClient(responses=[text_response("", stop_reason="refusal")])
    with pytest.raises(ClaudeJSONError, match="declined"):
        call_for_json(client, **ARGS)


def test_max_tokens_cutoff_surfaces_as_clean_error():
    client = FakeClient(responses=[text_response("{\"partial\":", stop_reason="max_tokens")])
    with pytest.raises(ClaudeJSONError, match="cut off"):
        call_for_json(client, **ARGS)


def test_history_prepended_to_messages():
    client = FakeClient(responses=[text_response({"ok": True})])
    history = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "old answer"}]
    call_for_json(client, **ARGS, history=history)
    sent = client.messages.calls[0]["messages"]
    assert len(sent) == 3 and sent[-1]["content"] == "hi"
