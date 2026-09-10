"""Tests for build_data_summary (analyst/insight_agent.py).

The core privacy/cost design decision is that the model sees a *compact summary*,
never the full dataset. These tests pin that contract: the summary names the
schema and shape, and stays bounded regardless of row count.
"""

from __future__ import annotations

import pandas as pd

from analyst import config
from analyst.insight_agent import build_data_summary, build_key_aggregates


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


def test_key_aggregates_expose_numeric_by_category(superstore_like_df):
    # The cross-tab view the univariate summary omits: sum of a measure per group.
    agg = build_key_aggregates(superstore_like_df)
    assert "Profit by Region (sum)" in agg
    # West = 20 + -5 = 15; East = 60. East should lead Profit, West lead Sales.
    region_line = next(ln for ln in agg.splitlines() if "Profit by Region" in ln)
    assert "'East'=60.00" in region_line
    # Groups are ranked descending by sum, so the leader appears first.
    assert region_line.index("'East'") < region_line.index("'West'")


def test_key_aggregates_skips_high_cardinality_and_empty():
    # An id-like column (every value unique) exceeds the cardinality cap and is
    # skipped; with no usable category the result is empty, not an error.
    df = pd.DataFrame({"Id": [f"u{i}" for i in range(50)], "Amount": range(50)})
    assert build_key_aggregates(df) == ""


def test_key_aggregates_drop_id_like_measures():
    # Row ID (near-unique) and Postal Code (name hint) are identifiers, not
    # metrics: they must not appear, so real measures keep their slots.
    df = pd.DataFrame(
        {
            "Region": ["West", "East", "West", "South"],
            "Row ID": [1, 2, 3, 4],
            "Postal Code": [90001, 10001, 90002, 30301],
            "Profit": [20.0, 60.0, -5.0, 10.0],
        }
    )
    agg = build_key_aggregates(df)
    assert "Profit by Region" in agg
    assert "Row ID by Region" not in agg
    assert "Postal Code by Region" not in agg


def test_key_aggregates_are_bounded(superstore_like_df):
    # Never more than max_dims * max_measures aggregate lines (+ 1 header).
    agg = build_key_aggregates(superstore_like_df)
    max_lines = 1 + config.QA_AGG_MAX_DIMS * config.QA_AGG_MAX_MEASURES
    assert agg.count("\n") + 1 <= max_lines
