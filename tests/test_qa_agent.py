"""Unit tests for the Q&A agent: memory trimming and the mocked answer path."""

from __future__ import annotations

import pytest

from analyst.qa_agent import QAError, answer_question, trim_history
from tests.conftest import FakeClient, text_response


def _turns(n: int) -> list[dict]:
    """n alternating user/assistant messages, user first."""
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(n)
    ]


def test_trim_history_noop_under_limit():
    history = _turns(4)
    assert trim_history(history, max_messages=10) == history


def test_trim_history_keeps_most_recent_and_starts_with_user():
    history = _turns(9)  # m0..m8, user on even indices
    trimmed = trim_history(history, max_messages=4)
    assert len(trimmed) <= 4
    assert trimmed[0]["role"] == "user"
    assert trimmed[-1] == history[-1]  # most recent turn survives


def test_answer_without_chart():
    client = FakeClient(responses=[text_response({"answer": "West leads.", "chart": None})])
    result = answer_question("Which region leads?", "summary text", client=client)
    assert result == {"answer": "West leads.", "chart": None}


def test_answer_with_chart_spec_passthrough():
    chart = {"kind": "bar", "x": "Region", "y": "Profit", "agg": "sum", "title": "Profit by region"}
    client = FakeClient(responses=[text_response({"answer": "See chart.", "chart": chart})])
    result = answer_question("Profit by region?", "summary", client=client)
    assert result["chart"] == chart


def test_history_is_sent_before_the_new_question():
    client = FakeClient(responses=[text_response({"answer": "ok", "chart": None})])
    history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    ]
    answer_question("follow-up", "summary", history=history, client=client)
    sent = client.messages.calls[0]["messages"]
    assert [m["content"] for m in sent] == ["first question", "first answer", "follow-up"]


def test_summary_lands_in_system_prompt_not_user_turn():
    client = FakeClient(responses=[text_response({"answer": "ok", "chart": None})])
    answer_question("q", "THE_SUMMARY_SENTINEL", client=client)
    call = client.messages.calls[0]
    assert "THE_SUMMARY_SENTINEL" in call["system"]


def test_missing_answer_raises_qa_error():
    client = FakeClient(responses=[
        text_response({"answer": "", "chart": None}),
        text_response({"answer": "", "chart": None}),  # helper may retry once
    ])
    with pytest.raises(QAError):
        answer_question("q", "summary", client=client)
