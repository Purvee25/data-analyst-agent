"""Pipeline: wires the insight-finder and critic agents into one call, with logging.

WHY this lives apart from app.py:
    app.py (Streamlit) should only wire UI to business logic. Keeping the actual
    "generate -> critique -> merge -> log" sequence here means it's importable
    and testable with zero Streamlit dependency, and the UI layer stays thin
    enough to audit for the error-handling requirements at a glance.
"""

from __future__ import annotations

import time

import anthropic
import pandas as pd

from .critic_agent import CriticReviewError, merge_insights_with_reviews, review_insights
from .insight_agent import InsightGenerationError, build_data_summary, generate_insights
from .logger import log_request


class PipelineError(Exception):
    """Raised when any stage of the insight pipeline fails.

    Wraps InsightGenerationError / CriticReviewError so callers (the Streamlit
    UI) only need to catch one exception type for "insight generation didn't
    work", regardless of which of the two underlying API calls failed.
    """


def run_insight_pipeline(df: pd.DataFrame, client: anthropic.Anthropic | None = None) -> list[dict]:
    """Full pipeline: summarize → LLM #1 (insight agent) → LLM #2 (critic) → merge + log."""
    start = time.monotonic()
    summary = build_data_summary(df)

    try:
        candidates = generate_insights(summary, client=client)       # LLM call 1: generate
        reviews = review_insights(candidates, summary, client=client) # LLM call 2: critique
    except (InsightGenerationError, CriticReviewError) as exc:
        log_request(
            "generate_insights",
            str(exc),
            success=False,
            response_time_seconds=time.monotonic() - start,
        )
        raise PipelineError(str(exc)) from exc

    final = merge_insights_with_reviews(candidates, reviews)  # rejected candidates dropped here
    elapsed = time.monotonic() - start
    avg_confidence = (
        sum(item["confidence"] for item in final) / len(final) if final else None  # logged for quality tracking
    )
    log_request(
        "generate_insights",
        f"{len(final)} of {len(candidates)} candidate insight(s) approved",
        success=True,
        response_time_seconds=elapsed,
        confidence_score=avg_confidence,
    )
    return final
