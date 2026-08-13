"""Tests for the insight pipeline orchestration (analyst/pipeline.py).

The pipeline wires generate -> critique -> merge -> log into one call. These
tests use the injectable FakeClient (no network) to verify the happy path,
the rejected-everything path, and that failures collapse into PipelineError.
"""

from __future__ import annotations

import pandas as pd
import pytest

from analyst import config, logger, pipeline
from analyst.insight_agent import InsightGenerationError
from tests.conftest import FakeClient, text_response

_CANDIDATES = {
    "insights": [
        {"insight": "West drives most profit.", "supporting_data": "West=0.45", "category": "comparison"},
        {"insight": "Sales trend up.", "supporting_data": "slope>0", "category": "trend"},
    ]
}


@pytest.fixture
def df():
    return pd.DataFrame({"Region": ["West", "East"], "Profit": [45.0, 10.0]})


@pytest.fixture(autouse=True)
def _isolate_log(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LOG_CSV_PATH", str(tmp_path / "requests.csv"))


def test_pipeline_merges_approved_and_downgraded(df):
    reviews = {"reviews": [
        {"index": 0, "verdict": "approve", "confidence": 0.9, "reasoning": "sound"},
        {"index": 1, "verdict": "reject", "confidence": 0.9, "reasoning": "n too small"},
    ]}
    client = FakeClient([text_response(_CANDIDATES), text_response(reviews)])

    final = pipeline.run_insight_pipeline(df, client=client)

    assert len(final) == 1  # the rejected candidate is dropped
    assert final[0]["critic_verdict"] == "approve"
    assert final[0]["confidence"] == 0.9


def test_pipeline_logs_one_row_per_run(df):
    reviews = {"reviews": [
        {"index": 0, "verdict": "approve", "confidence": 0.8, "reasoning": "ok"},
        {"index": 1, "verdict": "approve", "confidence": 0.6, "reasoning": "ok"},
    ]}
    client = FakeClient([text_response(_CANDIDATES), text_response(reviews)])

    pipeline.run_insight_pipeline(df, client=client)

    rows = pd.read_csv(config.LOG_CSV_PATH)
    assert len(rows) == 1
    assert rows.iloc[0]["action"] == "generate_insights"
    assert bool(rows.iloc[0]["success"]) is True


def test_pipeline_wraps_generation_failure(df):
    # First call returns malformed JSON twice -> InsightGenerationError inside,
    # surfaced to the caller as PipelineError.
    client = FakeClient([text_response("not json"), text_response("still not json")])
    with pytest.raises(pipeline.PipelineError):
        pipeline.run_insight_pipeline(df, client=client)

    rows = pd.read_csv(config.LOG_CSV_PATH)
    assert bool(rows.iloc[0]["success"]) is False


def test_insight_generation_error_is_pipeline_error_subclass_boundary(df, monkeypatch):
    def boom(*a, **k):
        raise InsightGenerationError("boom")

    monkeypatch.setattr(pipeline, "generate_insights", boom)
    with pytest.raises(pipeline.PipelineError, match="boom"):
        pipeline.run_insight_pipeline(df, client=FakeClient([]))
