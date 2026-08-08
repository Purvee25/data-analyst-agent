"""Side-effecting actions the agent may propose, gated behind human confirmation.

Extends the read-and-reason pipeline (insights, Q&A) with one real-world
action: emailing an approved insight via the local MCP server. Follows the
same declarative-spec pattern as the QA agent's charts:
    build a plain-dict spec -> guardrails validates it -> our own code
    executes it. The model (or code deriving from model output) never
    triggers the send directly.

WHY execute_action() takes no "are you sure" parameter:
    Confirmation is a UI concern (app.py renders a confirm/cancel step and
    only calls this function after the user clicks confirm). Baking a
    confirmed: bool flag in here would let a future caller bypass the human
    step by just passing True — keeping confirmation entirely in the caller
    means there is no such shortcut to bypass.
"""

from __future__ import annotations

from typing import Callable

from . import guardrails
from .mcp_client import MCPClientError, call_tool as _default_call_tool


class ActionError(Exception):
    """Raised when a confirmed action fails validation or execution."""


def build_email_alert_spec(insight: dict) -> dict:
    """Build a declarative email-alert action spec from one final insight dict."""
    category = insight.get("category", "Insight")
    subject = f"Data Analyst Alert: {category}"[: guardrails.MAX_ACTION_SUBJECT_LEN]
    body = "\n".join(
        [
            insight.get("insight", ""),
            "",
            f"Confidence: {insight.get('confidence', 0):.2f}",
            f"Supporting data: {insight.get('supporting_data', '—')}",
        ]
    )
    return {"action": "email_alert", "subject": subject, "body": body}


def execute_action(spec: dict, call_tool: Callable[..., str] = _default_call_tool) -> str:
    """Validate and execute an already-confirmed action spec.

    `call_tool` is injectable (defaults to the real MCP client) so tests can
    substitute a fake without spawning a subprocess or touching SMTP.
    """
    validated = guardrails.validate_action_spec(spec)

    if validated["action"] == "email_alert":
        try:
            return call_tool(
                "send_email_alert",
                {"subject": validated["subject"], "body": validated["body"]},
            )
        except MCPClientError as exc:
            raise ActionError(str(exc)) from exc

    raise ActionError(f"No executor wired up for action {validated['action']!r}.")
