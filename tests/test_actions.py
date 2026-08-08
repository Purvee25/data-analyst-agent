"""Unit tests for analyst/actions.py.

WHY these inject a fake call_tool instead of mocking analyst.mcp_client:
    execute_action() takes call_tool as a parameter specifically so tests
    never need to spawn the real MCP subprocess — same dependency-injection
    pattern as passing a fake Anthropic client to the insight/critic/QA
    agents (see tests/conftest.py).
"""

from __future__ import annotations

import pytest

from analyst.actions import ActionError, build_email_alert_spec, execute_action
from analyst.guardrails import ValidationError

APPROVED_INSIGHT = {
    "category": "Sales Trend",
    "insight": "West region profit margin dropped 12% in Q3.",
    "confidence": 0.87,
    "supporting_data": "West margin: 18% -> 6%, n=1,204 orders",
}


def test_build_email_alert_spec_shape():
    spec = build_email_alert_spec(APPROVED_INSIGHT)
    assert spec["action"] == "email_alert"
    assert "Sales Trend" in spec["subject"]
    assert "West region profit margin dropped 12%" in spec["body"]
    assert "0.87" in spec["body"]


def test_execute_action_calls_mcp_tool_with_no_recipient_field():
    captured = {}

    def fake_call_tool(tool_name, arguments):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        return "Email alert sent to ops@example.com."

    spec = build_email_alert_spec(APPROVED_INSIGHT)
    result = execute_action(spec, call_tool=fake_call_tool)

    assert result == "Email alert sent to ops@example.com."
    assert captured["tool_name"] == "send_email_alert"
    assert set(captured["arguments"].keys()) == {"subject", "body"}


def test_execute_action_rejects_invalid_spec_before_calling_tool():
    def fake_call_tool(tool_name, arguments):
        raise AssertionError("call_tool must not be invoked for an invalid spec")

    with pytest.raises(ValidationError):
        execute_action({"action": "delete_everything"}, call_tool=fake_call_tool)


def test_execute_action_wraps_mcp_client_error():
    from analyst.mcp_client import MCPClientError

    def failing_call_tool(tool_name, arguments):
        raise MCPClientError("SMTP connection refused")

    spec = build_email_alert_spec(APPROVED_INSIGHT)
    with pytest.raises(ActionError, match="SMTP connection refused"):
        execute_action(spec, call_tool=failing_call_tool)
