"""Tests for build_data_summary (analyst/insight_agent.py).

The core privacy/cost design decision is that the model sees a *compact summary*,
never the full dataset. These tests pin that contract: the summary names the
schema and shape, and stays bounded regardless of row count.
"""

from __future__ import annotations

import pandas as pd

from analyst import config
from analyst.insight_agent import build_data_summary


def test_summary_describes_shape_and_columns(superstore_like_df):
    summary = build_data_summary(superstore_like_df)
    assert isinstance(summary, str) and summary
    # Names the columns the model should reason about.
    for col in ["Region", "Category", "Sales", "Profit"]:
        assert col in summary


def test_summary_is_bounded_and_omits_bulk_rows():
    # A large frame must not blow up the summary — the model gets aggregates and
    # at most SAMPLE_ROWS_FOR_LLM sample rows, not all 10k rows.
    big = pd.DataFrame({"Region": ["West"] * 10_000, "Sales": range(10_000)})
    summary = build_data_summary(big)
    # Far smaller than dumping every value; a few KB, not hundreds.
    assert len(summary) < 8_000
    # The unique sentinel values from most rows are absent (not a full dump).
    assert "9999" not in summary or summary.count("\n") < config.SAMPLE_ROWS_FOR_LLM + 60
