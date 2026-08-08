"""Unit tests for the pure send_email() logic in the email-alert MCP server.

WHY these mock smtplib.SMTP instead of the MCP protocol layer:
    send_email() has no MCP/asyncio dependency by design (see that module's
    docstring) — testing it directly with a fake SMTP client covers all the
    interesting behaviour (missing config, SMTP failures, correct message
    construction) without the cost/flakiness of spawning a real subprocess.
"""

from __future__ import annotations

import smtplib

import pytest

from mcp_server.email_alert_server import EmailSendError, REQUIRED_ENV_VARS, send_email

FULL_ENV = {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "bot@example.com",
    "SMTP_PASSWORD": "secret",
    "ALERT_EMAIL_FROM": "bot@example.com",
    "ALERT_EMAIL_TO": "ops@example.com",
}


class FakeSMTP:
    """Records calls instead of touching the network. Supports the `with` protocol."""

    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.started_tls = False
        self.login_args = None
        self.sendmail_args = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def sendmail(self, from_addr, to_addrs, msg):
        self.sendmail_args = (from_addr, to_addrs, msg)


@pytest.fixture(autouse=True)
def _reset_fake_smtp():
    FakeSMTP.instances.clear()
    yield
    FakeSMTP.instances.clear()


def test_missing_env_vars_raises_clear_error(monkeypatch):
    for name in REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")  # leave the rest missing

    with pytest.raises(EmailSendError, match="Missing required SMTP env var"):
        send_email("subject", "body", smtp_client_factory=FakeSMTP)


def test_successful_send_uses_starttls_login_and_sendmail(monkeypatch):
    for name, value in FULL_ENV.items():
        monkeypatch.setenv(name, value)

    result = send_email("Alert!", "Something happened.", smtp_client_factory=FakeSMTP)

    assert "ops@example.com" in result
    smtp = FakeSMTP.instances[0]
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.started_tls is True
    assert smtp.login_args == ("bot@example.com", "secret")
    from_addr, to_addrs, msg = smtp.sendmail_args
    assert from_addr == "bot@example.com"
    assert to_addrs == ["ops@example.com"]
    assert "Alert!" in msg
    assert "Something happened." in msg


def test_smtp_failure_is_wrapped_in_email_send_error(monkeypatch):
    for name, value in FULL_ENV.items():
        monkeypatch.setenv(name, value)

    class RaisingSMTP(FakeSMTP):
        def login(self, username, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    with pytest.raises(EmailSendError, match="Failed to send email"):
        send_email("subject", "body", smtp_client_factory=RaisingSMTP)
