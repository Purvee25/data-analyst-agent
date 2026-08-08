"""Insight-finder agent: the first of two Claude API calls in the pipeline.

WHY the model sees a SUMMARY, never the raw dataset:
    1. Cost and token limits. The Superstore CSV is ~10K rows / 21 columns — sent
       as raw text that's tens of thousands of tokens, repeated on every insight
       request, for a session that may make many requests (see config.py's
       MAX_REQUESTS_PER_SESSION). A compact summary is a few hundred tokens and
       costs roughly the same regardless of whether the source file has 1K or 1M
       rows, which is what makes this design scale.
    2. It's a better *analytical* input, not just a cheaper one. An LLM reading
       10,000 raw rows doesn't compute aggregates any better than a human would by
       eyeballing a spreadsheet — it can only pattern-match on what's visible in
       its context, which is a poor substitute for an actual groupby/mean. Handing
       it pre-computed aggregates (means, top categories, counts) up front means
       every "insight" is grounded in a real, correct number pandas already
       calculated, not a statistic the model guessed at from a partial sample. The
       small row sample included alongside is for flavor/context (what does a row
       actually look like), not for the model to re-derive statistics from.
    3. This mirrors how a human analyst actually works: nobody stares at 10,000
       raw rows first. They start from `.describe()`, `.value_counts()`, and a
       `.head()` sample — exactly what build_data_summary() produces.

WHY a strict JSON schema (output_config.format) AND a manual parse-retry loop:
    The schema constrains the *shape* Claude is allowed to return, which removes
    an entire class of failures (prose wrapped around JSON, wrong field names,
    a category outside the enum). It does not remove every failure mode, though:
    a response can still be cut off by max_tokens, or refused by safety
    classifiers (stop_reason == "refusal", empty content). We handle both — the
    JSON-shape guarantee from the schema, and the truncation/refusal edge cases
    with an explicit retry — rather than picking one and hoping the other never
    happens in production.
"""

from __future__ import annotations

import anthropic
import pandas as pd

from . import config
from .claude_client import get_client
from .llm_json import ClaudeJSONError, call_for_json

VALID_CATEGORIES = ("trend", "anomaly", "comparison", "correlation")

INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "insight": {
                        "type": "string",
                        "description": "Plain English description of the finding.",
                    },
                    "supporting_data": {
                        "type": "string",
                        "description": "The specific numbers/stats from the summary that support this finding.",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(VALID_CATEGORIES),
                    },
                },
                "required": ["insight", "supporting_data", "category"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["insights"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are an experienced data analyst reviewing a dataset for the first time, \
with no prior question to answer. Your job is to proactively surface the most \
interesting and useful patterns a stakeholder would want to know about.

You will be given a compact statistical summary of a cleaned dataset: column \
names and types, summary statistics for numeric columns, top categories for \
categorical columns, and a small sample of rows for context.

Identify 3 to 5 candidate insights. Every insight must:
- Be directly supported by a specific number that appears in the summary you \
were given. Never invent or estimate a statistic that isn't shown.
- Be classified as one of: trend, anomaly, comparison, correlation.
- Be genuinely interesting to a business stakeholder, not a restatement of a \
single raw value (e.g. "there are 21 columns" is not an insight).

Do not hedge with disclaimers about needing more data — a separate review step \
handles statistical validity. Your job here is candidate generation only.
"""

class InsightGenerationError(Exception):
    """Raised when the insight agent cannot produce a usable set of insights.

    Callers (the pipeline in Phase 4, the Streamlit UI in Phase 5) catch this
    single exception type and show a clean, user-facing message rather than a
    raw traceback — the production-hardening error-handling requirement starts
    here, at the source of the failure.
    """


def _numeric_column_summary(series: pd.Series) -> str:
    described = series.describe()
    return (
        f"count={int(described['count'])}, mean={described['mean']:.2f}, "
        f"min={described['min']:.2f}, max={described['max']:.2f}"
    )


def _datetime_column_summary(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "no non-null values"
    return f"range={non_null.min().date()} to {non_null.max().date()}, count={len(non_null)}"


def _categorical_column_summary(series: pd.Series, top_n: int = 5) -> str:
    counts = series.value_counts().head(top_n)
    parts = [f"{val!r}: {count}" for val, count in counts.items()]
    return ", ".join(parts)


def build_data_summary(df: pd.DataFrame, sample_rows: int = config.SAMPLE_ROWS_FOR_LLM) -> str:
    """Turn a cleaned DataFrame into a compact, LLM-ready text summary.

    Kept as plain text (not JSON) because the insight agent consumes this as a
    prompt, not as structured data it parses in code — readability for the model
    (and for a human debugging a prompt) matters more here than machine parsing.
    """
    lines = [f"Dataset shape: {df.shape[0]} rows x {df.shape[1]} columns.", ""]
    lines.append("Columns and types:")
    for col in df.columns:
        lines.append(f"  - {col}: {df[col].dtype}")
    lines.append("")

    lines.append("Numeric column statistics:")
    numeric_cols = df.select_dtypes(include="number").columns
    if len(numeric_cols) == 0:
        lines.append("  (none)")
    for col in numeric_cols:
        lines.append(f"  - {col}: {_numeric_column_summary(df[col])}")
    lines.append("")

    lines.append("Date column ranges:")
    datetime_cols = df.select_dtypes(include="datetime").columns
    if len(datetime_cols) == 0:
        lines.append("  (none)")
    for col in datetime_cols:
        lines.append(f"  - {col}: {_datetime_column_summary(df[col])}")
    lines.append("")

    lines.append("Top categories for categorical columns:")
    categorical_cols = [
        c for c in df.select_dtypes(include="object").columns if df[c].nunique() <= 200
    ]
    if not categorical_cols:
        lines.append("  (none)")
    for col in categorical_cols:
        lines.append(f"  - {col}: {_categorical_column_summary(df[col])}")
    lines.append("")

    sample_n = min(sample_rows, len(df))
    lines.append(f"Sample of {sample_n} rows (for context, not for statistics):")
    if sample_n > 0:
        sample = df.sample(n=sample_n, random_state=42)
        lines.append(sample.to_string(index=False))
    else:
        lines.append("  (dataset is empty)")

    return "\n".join(lines)


def generate_insights(
    data_summary: str, client: anthropic.Anthropic | None = None
) -> list[dict]:
    """Call Claude to generate 3-5 candidate insights from a data summary.

    Every external call this function makes is wrapped so failures surface as a
    single InsightGenerationError with a clear message — callers never need to
    know about anthropic's exception hierarchy or the shared llm_json helper's
    ClaudeJSONError directly. See llm_json.py for the retry-on-malformed-JSON
    behavior shared with the critic agent.
    """
    client = client or get_client()
    user_content = f"Dataset summary:\n\n{data_summary}"

    try:
        parsed = call_for_json(
            client,
            model=config.CLAUDE_MODEL,
            max_tokens=config.INSIGHT_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            user_content=user_content,
            schema=INSIGHT_SCHEMA,
        )
    except ClaudeJSONError as exc:
        raise InsightGenerationError(str(exc)) from exc

    insights = parsed.get("insights")
    if not isinstance(insights, list):
        raise InsightGenerationError("Claude's response did not include an 'insights' list.")
    return insights
