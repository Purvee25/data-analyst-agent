"""Unit tests for api/chart_data.py — the JSON-chart twin of analyst/charts.py."""

from __future__ import annotations

import pandas as pd

from api.chart_data import MAX_BARS, chart_data


def test_bar_chart_sums_and_sorts_descending(superstore_like_df):
    spec = {"kind": "bar", "x": "Region", "y": "Sales", "agg": "sum", "title": "Sales by region"}
    result = chart_data(superstore_like_df, spec)
    assert result["kind"] == "bar"
    assert result["title"] == "Sales by region"
    values = [p["value"] for p in result["points"]]
    assert values == sorted(values, reverse=True)


def test_bar_values_match_pandas_groupby(superstore_like_df):
    spec = {"kind": "bar", "x": "Region", "y": "Sales", "agg": "sum", "title": ""}
    result = chart_data(superstore_like_df, spec)
    expected = superstore_like_df.groupby("Region")["Sales"].sum()
    got = {p["label"]: p["value"] for p in result["points"]}
    for label, value in expected.items():
        assert got[label] == round(float(value), 2)


def test_count_agg_needs_no_numeric_column(superstore_like_df):
    spec = {"kind": "bar", "x": "Category", "y": "Category", "agg": "count", "title": ""}
    result = chart_data(superstore_like_df, spec)
    assert sum(p["value"] for p in result["points"]) == len(superstore_like_df)


def test_high_cardinality_capped_at_max_bars():
    df = pd.DataFrame({"City": [f"City{i}" for i in range(40)], "Sales": range(40)})
    result = chart_data(df, {"kind": "bar", "x": "City", "y": "Sales", "agg": "sum", "title": ""})
    assert len(result["points"]) == MAX_BARS


def test_line_chart_over_dates_resamples_monthly(superstore_like_df):
    spec = {"kind": "line", "x": "Order Date", "y": "Sales", "agg": "sum", "title": "Trend"}
    result = chart_data(superstore_like_df, spec)
    assert len(result["points"]) == 3  # Jan, Feb, Mar
    assert result["points"][0]["label"] == "2024-01-01"


def test_line_chart_over_non_date_sorts_by_index():
    df = pd.DataFrame({"Rank": [3, 1, 2], "Score": [30, 10, 20]})
    result = chart_data(df, {"kind": "line", "x": "Rank", "y": "Score", "agg": "sum", "title": ""})
    labels = [p["label"] for p in result["points"]]
    assert labels == ["1", "2", "3"]


def test_missing_group_produces_null_value():
    df = pd.DataFrame({"Group": ["a", "a", "b"], "Value": [1.0, None, None]})
    result = chart_data(df, {"kind": "bar", "x": "Group", "y": "Value", "agg": "mean", "title": ""})
    got = {p["label"]: p["value"] for p in result["points"]}
    assert got["a"] == 1.0
    assert got["b"] is None
