"""Chart rendering: turns a validated chart spec into a matplotlib figure.

Core feature #6 (auto-generated charts).

WHY this is 100% our code and 0% model code:
    The Q&A agent emits a declarative spec (kind/x/y/agg/title) that
    guardrails.validate_chart_spec has already checked against a whitelist and
    the actual DataFrame. This module does the aggregation with pandas and the
    drawing with matplotlib — so every number on a chart is computed by real
    code from the real data, not asserted by a language model. The agent
    decides WHAT is worth plotting; it can never influence HOW it is computed.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless backend: Streamlit renders figures itself.

import matplotlib.pyplot as plt
import pandas as pd

# Cap on categorical bars so a high-cardinality column (e.g. City) yields a
# readable "top N" chart instead of an unreadable smear.
MAX_BARS = 12


def _aggregate(df: pd.DataFrame, spec: dict) -> pd.Series:
    x, y, agg = spec["x"], spec["y"], spec["agg"]
    grouped = df.groupby(x, dropna=True)
    if agg == "count":
        return grouped.size()
    return getattr(grouped[y], agg)()


def render_chart(df: pd.DataFrame, spec: dict) -> plt.Figure:
    """Render a validated chart spec into a matplotlib Figure.

    Assumes guardrails.validate_chart_spec(spec, df) has already passed —
    this function only handles presentation choices (sorting, top-N capping,
    monthly resampling for dates), never validation.
    """
    kind, x, agg = spec["kind"], spec["x"], spec["agg"]
    y_label = "row count" if agg == "count" else f"{agg} of {spec['y']}"

    fig, ax = plt.subplots(figsize=(8, 4.5))

    if kind == "line" and pd.api.types.is_datetime64_any_dtype(df[x]):
        # Trend over time: resample monthly so daily noise doesn't bury the trend.
        ts = df.set_index(x)
        series = (
            ts.resample("MS").size()
            if agg == "count"
            else getattr(ts[spec["y"]].resample("MS"), agg)()
        )
        ax.plot(series.index, series.values, marker="o", markersize=3)
    else:
        series = _aggregate(df, spec)
        if kind == "line":
            series = series.sort_index()
            ax.plot(series.index.astype(str), series.values, marker="o", markersize=3)
        else:
            series = series.sort_values(ascending=False).head(MAX_BARS)
            ax.bar(series.index.astype(str), series.values)
            if len(series) > 4:
                ax.tick_params(axis="x", rotation=45)
                for label in ax.get_xticklabels():
                    label.set_horizontalalignment("right")

    ax.set_title(spec.get("title") or f"{y_label} by {x}")
    ax.set_xlabel(x)
    ax.set_ylabel(y_label)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig
