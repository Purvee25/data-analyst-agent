"""Unit tests for the critic agent's decision logic and (mocked) API path."""

from __future__ import annotations

from analyst.critic_agent import (
    apply_verdict,
    merge_insights_with_reviews,
    review_insights,
)
from tests.conftest import FakeClient, text_response

INSIGHT = {"insight": "West is most profitable", "supporting_data": "mean=42", "category": "comparison"}


def test_approve_keeps_insight_with_confidence():
    merged = apply_verdict(INSIGHT, {"verdict": "approve", "confidence": 0.9, "reasoning": "solid"})
    assert merged["confidence"] == 0.9
    assert merged["critic_verdict"] == "approve"
    assert merged["critic_reasoning"] == "solid"


def test_reject_drops_insight():
    assert apply_verdict(INSIGHT, {"verdict": "reject", "confidence": 0.9, "reasoning": "n=3"}) is None


def test_downgrade_caps_confidence_at_half():
    merged = apply_verdict(INSIGHT, {"verdict": "downgrade", "confidence": 0.95, "reasoning": "overstated"})
    assert merged["confidence"] == 0.5  # downgrade must actually lower displayed confidence


def test_unknown_verdict_treated_as_downgrade_not_approve():
    merged = apply_verdict(INSIGHT, {"verdict": "ship it!", "confidence": 0.9, "reasoning": ""})
    assert merged["critic_verdict"] == "downgrade"
    assert merged["confidence"] <= 0.5


def test_confidence_clamped_to_unit_interval():
    assert apply_verdict(INSIGHT, {"verdict": "approve", "confidence": 1.7, "reasoning": ""})["confidence"] == 1.0
    assert apply_verdict(INSIGHT, {"verdict": "approve", "confidence": -0.2, "reasoning": ""})["confidence"] == 0.0
    assert apply_verdict(INSIGHT, {"verdict": "approve", "confidence": "high", "reasoning": ""})["confidence"] == 0.0


def test_merge_drops_unreviewed_insights():
    insights = [INSIGHT, {**INSIGHT, "insight": "second"}]
    reviews = [{"index": 1, "verdict": "approve", "confidence": 0.8, "reasoning": "ok"}]
    final = merge_insights_with_reviews(insights, reviews)
    assert len(final) == 1
    assert final[0]["insight"] == "second"  # index-0 insight was never reviewed → dropped


def test_review_insights_empty_list_makes_no_api_call():
    client = FakeClient(responses=[])  # any call would raise "ran out of responses"
    assert review_insights([], "summary", client=client) == []
    assert client.messages.calls == []


def test_review_insights_parses_mocked_response():
    payload = {"reviews": [{"index": 0, "verdict": "approve", "confidence": 0.85, "reasoning": "fine"}]}
    client = FakeClient(responses=[text_response(payload)])
    reviews = review_insights([INSIGHT], "summary", client=client)
    assert reviews[0]["verdict"] == "approve"
    # The critic must have been shown the data summary, not just the claims.
    assert "summary" in client.messages.calls[0]["messages"][-1]["content"]
