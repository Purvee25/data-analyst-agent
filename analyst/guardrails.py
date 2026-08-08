"""Guardrails: input validation + destructive-operation blocking.

Production hardening requirements #8 (input validation) and #9 (guardrails).

WHY these are pure functions with no Streamlit/API imports:
    Guardrails are exactly the code you most want unit-tested. Keeping them free
    of UI and network dependencies means every rule here is testable with a
    plain assert, and the same checks can protect a future CLI or API entry
    point without modification.

WHY a blocklist for destructive text even though this app never executes
generated code:
    Defence in depth. Today the agents only ever *describe* data (the chart
    spec is validated against a whitelist and executed by our own pandas code,
    never by anything the model wrote). But requirements evolve — if someone
    later adds a "run this pandas expression" feature, the guardrail is already
    in the request path rather than being a TODO. It also blocks prompt-abuse
    questions ("ignore your instructions and DROP TABLE...") before they spend
    a rate-limited API call.
"""

from __future__ import annotations

import re

import pandas as pd

from . import config


class ValidationError(Exception):
    """Raised when an upload or request fails validation.

    Carries a user-facing message — callers can show str(exc) directly without
    leaking internals.
    """


# Patterns that indicate an attempt at a destructive or code-execution style
# operation. Matched case-insensitively against user questions. Word-boundary
# anchored so ordinary analytics language ("drop-off in sales") doesn't trip.
_DESTRUCTIVE_PATTERNS = [
    r"\bdrop\s+(table|database|column)\b",
    r"\bdelete\s+from\b",
    r"\btruncate\s+table\b",
    r"\balter\s+table\b",
    r"\bos\.system\b",
    r"\bsubprocess\b",
    r"\b__import__\b",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\brm\s+-rf\b",
    r"\bshutil\.rmtree\b",
    r"\bto_sql\b",
    r"\bpickle\.loads\b",
]

_DESTRUCTIVE_RE = re.compile("|".join(_DESTRUCTIVE_PATTERNS), re.IGNORECASE)

# Chart-spec whitelist: the QA agent may only *request* charts assembled from
# these parts. Our own code does the aggregation — the model never supplies
# executable code, only column names and an aggregation keyword.
ALLOWED_CHART_KINDS = ("bar", "line")
ALLOWED_AGGS = ("sum", "mean", "count")

# Action-spec whitelist: the only side-effecting action the agent may propose
# is a pre-approved kind, executed only after a human confirms in the UI (see
# app.py). Note there is no "to"/recipient field here at all — the
# destination is operator config (analyst/config.ALERT_EMAIL_TO / the MCP
# server's own env), never something the spec carries. See
# mcp_server/email_alert_server.py for why.
ALLOWED_ACTIONS = ("email_alert",)
MAX_ACTION_SUBJECT_LEN = 200
MAX_ACTION_BODY_LEN = 4000


def is_destructive(text: str) -> bool:
    """Return True if the text looks like a destructive / code-exec attempt."""
    if not isinstance(text, str):
        return False
    return bool(_DESTRUCTIVE_RE.search(text))


def validate_upload(raw: bytes, filename: str = "") -> None:
    """Validate an uploaded file's size and extension before parsing.

    Raises ValidationError with a clean, user-facing message on any failure.
    Checked BEFORE pandas ever sees the bytes, so an oversized or wrong-type
    file costs nothing to reject.
    """
    if not raw:
        raise ValidationError("The uploaded file is empty.")
    if len(raw) > config.MAX_UPLOAD_BYTES:
        mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationError(
            f"File is {len(raw) / (1024 * 1024):.1f} MB, which exceeds the {mb} MB limit."
        )
    if filename and not filename.lower().endswith(".csv"):
        raise ValidationError("Only .csv files are supported.")


def validate_row_count(df: pd.DataFrame) -> None:
    """Reject DataFrames over the row cap (protects memory + summary size)."""
    if len(df) > config.MAX_ROWS:
        raise ValidationError(
            f"Dataset has {len(df):,} rows, which exceeds the {config.MAX_ROWS:,} row limit."
        )


def validate_question(question: str) -> None:
    """Validate a user's natural-language question before it reaches Claude."""
    if not question or not question.strip():
        raise ValidationError("Please enter a question.")
    if len(question) > 2000:
        raise ValidationError("Question is too long (2,000 character limit).")
    if is_destructive(question):
        raise ValidationError(
            "That question looks like it requests a destructive or code-execution "
            "operation, which this analyst does not perform."
        )


def validate_chart_spec(spec: dict, df: pd.DataFrame) -> dict:
    """Validate a model-emitted chart spec against the whitelist and the data.

    Returns the validated spec. Raises ValidationError if the spec asks for
    anything outside the whitelist or references columns that don't exist —
    the model only ever *names* columns and an aggregation; it never supplies
    code we would run.
    """
    if not isinstance(spec, dict):
        raise ValidationError("Chart spec must be an object.")

    kind = spec.get("kind")
    if kind not in ALLOWED_CHART_KINDS:
        raise ValidationError(f"Chart kind must be one of {ALLOWED_CHART_KINDS}.")

    agg = spec.get("agg")
    if agg not in ALLOWED_AGGS:
        raise ValidationError(f"Aggregation must be one of {ALLOWED_AGGS}.")

    x, y = spec.get("x"), spec.get("y")
    if x not in df.columns:
        raise ValidationError(f"Chart references unknown column {x!r}.")
    # count doesn't need a numeric y column; sum/mean do.
    if agg != "count":
        if y not in df.columns:
            raise ValidationError(f"Chart references unknown column {y!r}.")
        if not pd.api.types.is_numeric_dtype(df[y]):
            raise ValidationError(f"Column {y!r} is not numeric and cannot be aggregated with {agg!r}.")

    return spec


def validate_action_spec(spec: dict) -> dict:
    """Validate a proposed side-effecting action before it reaches execution.

    Returns a NEW dict containing only the whitelisted fields (action,
    subject, body) — same "never trust more than we checked" pattern as
    validate_chart_spec. Callers must still gate execution behind an explicit
    human confirmation; this function only checks content, not consent.
    """
    if not isinstance(spec, dict):
        raise ValidationError("Action spec must be an object.")

    action = spec.get("action")
    if action not in ALLOWED_ACTIONS:
        raise ValidationError(f"Action must be one of {ALLOWED_ACTIONS}.")

    subject, body = spec.get("subject"), spec.get("body")
    if not isinstance(subject, str) or not subject.strip():
        raise ValidationError("Action subject must be non-empty text.")
    if not isinstance(body, str) or not body.strip():
        raise ValidationError("Action body must be non-empty text.")
    if len(subject) > MAX_ACTION_SUBJECT_LEN:
        raise ValidationError(f"Action subject exceeds {MAX_ACTION_SUBJECT_LEN} characters.")
    if len(body) > MAX_ACTION_BODY_LEN:
        raise ValidationError(f"Action body exceeds {MAX_ACTION_BODY_LEN} characters.")
    if is_destructive(subject) or is_destructive(body):
        raise ValidationError(
            "Action content looks like a destructive or code-execution operation."
        )

    return {"action": action, "subject": subject, "body": body}
