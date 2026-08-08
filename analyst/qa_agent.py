"""Q&A agent: natural-language follow-up questions with session memory.

Core feature #5 (NL Q&A + conversation memory) and #6 (auto-charts).

WHY the agent emits a chart SPEC instead of chart code:
    Letting an LLM write matplotlib code that we then exec() would undo every
    guardrail in this project. Instead the model returns a tiny declarative
    spec — {"kind": "bar", "x": "Region", "y": "Profit", "agg": "sum"} — which
    guardrails.validate_chart_spec checks against a whitelist and charts.py
    renders with OUR pandas/matplotlib code. The model chooses WHAT to plot;
    it never supplies anything executable.

WHY memory is a plain trimmed message list, not a vector store:
    Session memory here means "remember what we discussed this session" —
    resending the last N turns is the simplest mechanism that fully satisfies
    that, and it is bounded (config.QA_HISTORY_MAX_MESSAGES) so cost per
    follow-up cannot grow without limit. Retrieval infrastructure would add
    moving parts without adding capability at this scale.
"""

from __future__ import annotations

import anthropic

from . import config
from .claude_client import get_client
from .llm_json import ClaudeJSONError, call_for_json

QA_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "Plain English answer to the user's question, grounded in the dataset summary.",
        },
        "chart": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["bar", "line"]},
                        "x": {
                            "type": "string",
                            "description": "Exact column name to group by (a categorical or date column).",
                        },
                        "y": {
                            "type": "string",
                            "description": "Exact numeric column name to aggregate. For agg='count', repeat the x column.",
                        },
                        "agg": {"type": "string", "enum": ["sum", "mean", "count"]},
                        "title": {"type": "string"},
                    },
                    "required": ["kind", "x", "y", "agg", "title"],
                    "additionalProperties": False,
                },
                {"type": "null"},
            ],
            "description": "A chart spec if a chart would help answer the question (aggregates, trends, comparisons); null otherwise.",
        },
    },
    "required": ["answer", "chart"],
    "additionalProperties": False,
}

SYSTEM_PROMPT_TEMPLATE = """\
You are a data analyst answering follow-up questions about a dataset the user \
has uploaded. You have been given a statistical summary of the cleaned data.

Rules:
- Ground every numeric claim in the summary below. If the summary does not \
contain the information needed to answer precisely, say so plainly and answer \
with what IS available — never invent a number.
- Use the conversation history: the user may refer back to earlier answers \
("what about the West region?" after asking about profit).
- Propose a chart (set the "chart" field) when the question is about an \
aggregate, trend over time, or comparison across categories. Use EXACT column \
names from the summary. Use a "line" chart with a date column as x for trends, \
and a "bar" chart otherwise. Set chart to null for questions a sentence \
answers fully.
- Keep answers concise: a stakeholder should get the point in 2-4 sentences.

Dataset summary:

{data_summary}
"""


class QAError(Exception):
    """Raised when the Q&A agent cannot produce a usable answer.

    Same pattern as InsightGenerationError / CriticReviewError: the UI catches
    one exception type per feature and shows str(exc), never a traceback.
    """


def trim_history(history: list[dict], max_messages: int = config.QA_HISTORY_MAX_MESSAGES) -> list[dict]:
    """Keep only the most recent messages, preserving user/assistant alternation.

    Trimming from the FRONT keeps the recent context (what a follow-up question
    most likely refers to). If the cut would land on an assistant message
    (breaking the required user-first alternation), drop one more.
    """
    if len(history) <= max_messages:
        return list(history)
    trimmed = history[-max_messages:]
    while trimmed and trimmed[0].get("role") != "user":
        trimmed = trimmed[1:]
    return trimmed


def answer_question(
    question: str,
    data_summary: str,
    history: list[dict] | None = None,
    client: anthropic.Anthropic | None = None,
) -> dict:
    """Answer one follow-up question. Returns {"answer": str, "chart": dict | None}.

    The caller owns the history list (Streamlit session state); this function
    is stateless so it stays trivially testable. The chart spec, if any, is
    NOT yet validated against the DataFrame — the caller must pass it through
    guardrails.validate_chart_spec before rendering.
    """
    client = client or get_client()
    system = SYSTEM_PROMPT_TEMPLATE.format(data_summary=data_summary)

    try:
        parsed = call_for_json(
            client,
            model=config.CLAUDE_MODEL,
            max_tokens=config.QA_MAX_TOKENS,
            system=system,
            user_content=question,
            schema=QA_SCHEMA,
            history=trim_history(history or []),
        )
    except ClaudeJSONError as exc:
        raise QAError(str(exc)) from exc

    answer = parsed.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise QAError("Claude's response did not include an answer.")

    chart = parsed.get("chart")
    if not isinstance(chart, dict):
        chart = None
    return {"answer": answer, "chart": chart}
