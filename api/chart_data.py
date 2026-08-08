"""Turn a validated chart spec into JSON-serialisable chart data.

WHY this exists alongside analyst/charts.py:
    charts.py renders a matplotlib PNG (what Streamlit needed). The React
    frontend renders charts itself (Recharts), so it needs the aggregated
    numbers as arrays, not an image. This module reuses the exact same
    aggregation rules — top-N capping for bars, monthly resampling for date
    lines — so a chart looks identical no matter which frontend draws it.
    The model still only ever supplies a whitelisted spec; the aggregation is
    100% our pandas code.
"""

from __future__ import annotations

import pandas as pd

# Mirror charts.MAX_BARS so the React bar chart caps high-cardinality columns
# (e.g. City) to a readable "top N" exactly like the matplotlib version did.
MAX_BARS = 12


def chart_data(df: pd.DataFrame, spec: dict) -> dict:
    """Aggregate `df` per a validated spec into {labels, values, ...} for JSON.

    Assumes guardrails.validate_chart_spec(spec, df) has already passed. Returns
    a dict the frontend can hand straight to a charting component:
        {kind, title, x_label, y_label, points: [{label, value}, ...]}
    """
    kind, x, agg = spec["kind"], spec["x"], spec["agg"]
    y_label = "row count" if agg == "count" else f"{agg} of {spec['y']}"

    if kind == "line" and pd.api.types.is_datetime64_any_dtype(df[x]):
        # Trend over time: resample monthly so daily noise doesn't bury the trend.
        ts = df.set_index(x)
        series = (
            ts.resample("MS").size()
            if agg == "count"
            else getattr(ts[spec["y"]].resample("MS"), agg)()
        )
        labels = [d.date().isoformat() for d in series.index]
    else:
        grouped = df.groupby(x, dropna=True)
        series = grouped.size() if agg == "count" else getattr(grouped[spec["y"]], agg)()
        if kind == "line":
            series = series.sort_index()
        else:
            series = series.sort_values(ascending=False).head(MAX_BARS)
        labels = [str(i) for i in series.index]

    points = [
        {"label": label, "value": (None if pd.isna(v) else round(float(v), 2))}
        for label, v in zip(labels, series.values)
    ]
    return {
        "kind": kind,
        "title": spec.get("title") or f"{y_label} by {x}",
        "x_label": x,
        "y_label": y_label,
        "points": points,
    }
