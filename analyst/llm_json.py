"""Shared helper for Claude calls constrained to a JSON schema.

WHY this is factored out of insight_agent.py rather than living there:
    The critic agent (a second, independent Claude call) needs the exact same
    control flow: call with output_config.format, handle refusal/max_tokens,
    parse the JSON, retry once with a clarifying instruction on failure, then
    give up with a clear error. Duplicating that flow across two files invites
    them to silently diverge (e.g. one gets a bugfix to the retry logic, the
    other doesn't). One shared function means both agents share one contract.
"""

from __future__ import annotations

import json

import anthropic

# appended on retry — tells Claude to drop prose/markdown and return raw JSON only
CLARIFY_SUFFIX = """

Your previous response could not be parsed as valid JSON. Respond again with \
ONLY the JSON object described by the schema — no prose, no markdown code \
fences, no explanation before or after.
"""


class ClaudeJSONError(Exception):
    """Raised when a schema-constrained Claude call fails or can't be parsed,
    even after one retry. Callers wrap this in their own domain-specific
    exception (InsightGenerationError, CriticReviewError, ...) so a consumer
    never needs to know this shared helper exists.
    """


def _extract_text(response: anthropic.types.Message) -> str:
    # safety refusal = Claude declined due to content policy
    if response.stop_reason == "refusal":
        raise ClaudeJSONError("Claude declined to respond (safety refusal).")
    # max_tokens = response cut off mid-JSON; parsing would fail anyway
    if response.stop_reason == "max_tokens":
        raise ClaudeJSONError(
            "Claude's response was cut off before completing (max_tokens reached)."
        )
    text = next((block.text for block in response.content if block.type == "text"), None)
    if not text:
        raise ClaudeJSONError("Claude returned no text content.")
    return text


def _try_parse(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None  # caller decides whether to retry


def call_for_json(
    client: anthropic.Anthropic,
    *,
    model: str,
    max_tokens: int,
    system: str,
    user_content: str,
    schema: dict,
    history: list[dict] | None = None,
) -> dict:
    """Call Claude with a JSON schema constraint; parse and retry once on failure.

    history = prior messages; used by Q&A agent for session memory.
    insight/critic agents pass no history — each call is fully independent.
    Always raises ClaudeJSONError, never a raw SDK exception or json.JSONDecodeError.
    """

    def _do(content: str) -> anthropic.types.Message:
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            # history (if any) prepended so Q&A agent remembers prior turns
            messages=[*(history or []), {"role": "user", "content": content}],
            # json_schema forces the API to return valid JSON matching our schema
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )

    try:
        response = _do(user_content)  # attempt 1
    except (anthropic.APIError, OSError) as exc:
        raise ClaudeJSONError(f"Claude API request failed: {exc}") from exc

    text = _extract_text(response)
    parsed = _try_parse(text)

    if parsed is None:
        # attempt 2 — append CLARIFY_SUFFIX to fix malformed JSON
        try:
            response = _do(user_content + CLARIFY_SUFFIX)
        except (anthropic.APIError, OSError) as exc:
            raise ClaudeJSONError(f"Claude API retry failed: {exc}") from exc
        text = _extract_text(response)
        parsed = _try_parse(text)

    if parsed is None:
        # failed twice — give up rather than looping indefinitely
        raise ClaudeJSONError("Claude returned malformed JSON twice in a row; giving up.")

    return parsed
