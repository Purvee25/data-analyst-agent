"""Critic agent: a SECOND, independent Claude API call that reviews the insight
agent's candidate insights for statistical validity.

WHY two separate API calls instead of one call that "generates and self-checks":
    A single model asked to both invent insights and judge them is grading its own
    homework in the same breath — whatever bias or overreach produced a shaky
    insight (extrapolating from a 3-row sample, mistaking correlation for
    causation) is exactly the bias most likely to also approve it if it's judging
    within the same turn. Making the critic a genuinely separate request means it
    starts from a blank context, is prompted with a skeptical, statistically-
    literate persona, and never sees the insight agent's own reasoning — only its
    final claims plus the same underlying data summary. That separation is what
    makes "approve / reject / downgrade" a real check rather than a formality.

WHY the critic gets the data summary too, not just the insight text:
    Judging "is this insight actually supported by the data" requires seeing the
    data it's supposed to be supported by. Without the summary, the critic could
    only check internal consistency (does the insight's own supporting_data
    string sound plausible), not whether that number is actually the one Claude
    computed — the point of a critic is external validation, not vibes.
"""

from __future__ import annotations

import anthropic

from . import config
from .claude_client import get_client
from .llm_json import ClaudeJSONError, call_for_json

VALID_VERDICTS = ("approve", "reject", "downgrade")

CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "0-based index matching the insight's position in the numbered list you were given.",
                    },
                    "verdict": {
                        "type": "string",
                        "enum": list(VALID_VERDICTS),
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Your confidence, from 0.0 to 1.0, that this insight is statistically sound and worth showing to a stakeholder.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Your statistical reasoning for the verdict — what you checked and why.",
                    },
                },
                "required": ["index", "verdict", "confidence", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["reviews"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are a skeptical senior data analyst reviewing a colleague's candidate \
insights before they go to a stakeholder. You did not generate these insights \
and have no attachment to them — your job is to find problems, not to be nice.

For each candidate insight, check specifically for:
- Sample size: is the group behind this insight large enough to be meaningful, \
or could it be noise from a handful of rows?
- Correlation vs. causation: does the insight claim or imply that one thing \
causes another when the data only shows they co-occur?
- Cherry-picked timeframe: does the insight rely on a narrow date range or a \
single category that was likely selected because it looks interesting, rather \
than being representative?
- Actually supported by the data shown: does the "supporting_data" field cite a \
number that genuinely appears in the dataset summary you were given, or does it \
look invented or extrapolated beyond what the summary shows?

For each insight, return a verdict:
- "approve": statistically sound as stated, no material concerns.
- "downgrade": the core finding is plausible but overstated, imprecise, or has a \
minor caveat — keep it, but your confidence score should reflect the concern.
- "reject": the insight is unsupported, misleading, or not statistically \
meaningful — it should not be shown to a stakeholder.

confidence must be a number between 0.0 and 1.0. Be specific in your reasoning — \
name the actual concern, don't just restate the verdict.
"""


class CriticReviewError(Exception):
    """Raised when the critic agent cannot produce a usable set of reviews.

    Mirrors InsightGenerationError's role: callers catch this one type instead
    of reaching into the shared llm_json helper's exception.
    """


def _build_user_content(insights: list[dict], data_summary: str) -> str:
    lines = [f"Dataset summary:\n\n{data_summary}", "", "Candidate insights to review:"]
    for i, item in enumerate(insights):
        lines.append(
            f"{i}. [{item.get('category')}] {item.get('insight')}\n"
            f"   Supporting data: {item.get('supporting_data')}"
        )
    return "\n".join(lines)


def review_insights(
    insights: list[dict], data_summary: str, client: anthropic.Anthropic | None = None
) -> list[dict]:
    """Call Claude to review each candidate insight and return a list of reviews.

    Returns an empty list without making an API call if `insights` is empty —
    there is nothing to critique, and spending a request to confirm that would
    just burn a slot in the session's rate limit for no reason.
    """
    if not insights:
        return []

    client = client or get_client()
    user_content = _build_user_content(insights, data_summary)

    try:
        parsed = call_for_json(
            client,
            model=config.CLAUDE_MODEL,
            max_tokens=config.CRITIC_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            user_content=user_content,
            schema=CRITIC_SCHEMA,
        )
    except ClaudeJSONError as exc:
        raise CriticReviewError(str(exc)) from exc

    reviews = parsed.get("reviews")
    if not isinstance(reviews, list):
        raise CriticReviewError("Claude's response did not include a 'reviews' list.")
    return reviews


def apply_verdict(insight: dict, review: dict) -> dict | None:
    """Merge one critic review into its insight, or return None if rejected.

    This is deliberately a plain, side-effect-free function (no API call, no
    randomness) — it's the actual decision logic (keep or drop? what confidence?)
    and is the piece worth unit testing in isolation, independent of mocking any
    network call.
    """
    verdict = review.get("verdict")
    if verdict not in VALID_VERDICTS:
        verdict = "downgrade"  # an unrecognized verdict is treated cautiously, not trusted as approve.

    if verdict == "reject":
        return None

    # Clamp defensively: the schema asks for 0.0-1.0 but structured outputs don't
    # enforce numeric ranges (only additionalProperties/enum/required are
    # guaranteed), so a stray 1.2 or -0.1 from the model must not leak into the UI.
    confidence = review.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    if verdict == "downgrade":
        # A "downgrade" verdict must actually lower displayed confidence — otherwise
        # the distinction between "approve" and "downgrade" is cosmetic only.
        confidence = min(confidence, 0.5)

    merged = dict(insight)
    merged["confidence"] = confidence
    merged["critic_verdict"] = verdict
    merged["critic_reasoning"] = review.get("reasoning", "")
    return merged


def merge_insights_with_reviews(insights: list[dict], reviews: list[dict]) -> list[dict]:
    """Combine candidate insights with their critic reviews into the final list.

    Insights the critic didn't review at all (a missing index — the model
    skipped one, or review count didn't match) are dropped rather than shown
    unvetted: publishing an insight nobody actually checked defeats the purpose
    of having a critic in the first place.
    """
    reviews_by_index = {
        review.get("index"): review for review in reviews if isinstance(review.get("index"), int)
    }

    final: list[dict] = []
    for i, insight in enumerate(insights):
        review = reviews_by_index.get(i)
        if review is None:
            continue
        merged = apply_verdict(insight, review)
        if merged is not None:
            final.append(merged)
    return final
