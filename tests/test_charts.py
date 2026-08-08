"""Unit tests for chart rendering — every figure is computed by pandas, not the model."""

from __future__ import annotations

import matplotlib.pyplot as plt

from analyst.charts import MAX_BARS, render_chart


def test_bar_chart_renders(superstore_like_df):
    spec = {"kind": "bar", "x": "Region", "y": "Profit", "agg": "sum", "title": "Profit by region"}
    fig = render_chart(superstore_like_df, spec)
    ax = fig.axes[0]
    assert ax.get_title() == "Profit by region"
    assert len(ax.patches) == superstore_like_df["Region"].nunique()
    plt.close(fig)


def test_bar_values_match_pandas_groupby(superstore_like_df):
    spec = {"kind": "bar", "x": "Region", "y": "Sales", "agg": "sum", "title": ""}
    fig = render_chart(superstore_like_df, spec)
    heights = sorted(p.get_height() for p in fig.axes[0].patches)
    expected = sorted(superstore_like_df.groupby("Region")["Sales"].sum().values)
    assert heights == expected
    plt.close(fig)


def test_line_chart_over_dates_resamples_monthly(superstore_like_df):
    spec = {"kind": "line", "x": "Order Date", "y": "Sales", "agg": "sum", "title": "Trend"}
    fig = render_chart(superstore_like_df, spec)
    line = fig.axes[0].lines[0]
    assert len(line.get_ydata()) == 3  # Jan, Feb, Mar
    plt.close(fig)


def test_count_agg_needs_no_numeric_column(superstore_like_df):
    spec = {"kind": "bar", "x": "Category", "y": "Category", "agg": "count", "title": ""}
    fig = render_chart(superstore_like_df, spec)
    assert sum(p.get_height() for p in fig.axes[0].patches) == len(superstore_like_df)
    plt.close(fig)


def test_high_cardinality_capped_at_max_bars(superstore_like_df):
    import pandas as pd

    df = pd.DataFrame({"City": [f"City{i}" for i in range(40)], "Sales": range(40)})
    fig = render_chart(df, {"kind": "bar", "x": "City", "y": "Sales", "agg": "sum", "title": ""})
    assert len(fig.axes[0].patches) == MAX_BARS
    plt.close(fig)
