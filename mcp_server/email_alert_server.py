"""Local MCP server exposing one tool: send_email_alert.

Spawned as a subprocess over stdio by analyst/mcp_client.py — this is the
Model Context Protocol's standard local-tool transport. Can also be run
standalone for manual testing:

    python -m mcp_server.email_alert_server

WHY the recipient address is read from THIS process's own environment
instead of being accepted as a tool argument:
    subject/body are the only inputs a caller (ultimately, an LLM-influenced
    insight) can supply. If "to" were also an argument, a prompt-injected
    insight could redirect an alert to an attacker-controlled address. The
    destination is operator config, not agent output — same trust boundary
    the chart-spec whitelist in guardrails.py enforces for chart requests.

WHY send_email() is a plain function separate from the @mcp.tool wrapper:
    It has no MCP/asyncio dependency, so it's testable with a one-line mock
    of smtplib.SMTP instead of spinning up the MCP protocol machinery.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

from mcp.server.fastmcp import FastMCP

REQUIRED_ENV_VARS = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "ALERT_EMAIL_FROM",
    "ALERT_EMAIL_TO",
)


class EmailSendError(Exception):
    """Raised when SMTP config is missing or the send itself fails."""


def _smtp_config() -> dict[str, str]:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise EmailSendError(
            f"Missing required SMTP env var(s): {', '.join(missing)}. "
            "Set them before running the email-alert MCP server."
        )
    return {name: os.environ[name] for name in REQUIRED_ENV_VARS}


def send_email(subject: str, body: str, smtp_client_factory=smtplib.SMTP) -> str:
    """Send a plain-text email via SMTP with STARTTLS. Returns a confirmation string.

    `smtp_client_factory` is injectable so tests can substitute a fake SMTP
    client without touching the network.
    """
    cfg = _smtp_config()
    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = cfg["ALERT_EMAIL_FROM"]
    message["To"] = cfg["ALERT_EMAIL_TO"]

    try:
        with smtp_client_factory(cfg["SMTP_HOST"], int(cfg["SMTP_PORT"]), timeout=15) as server:
            server.starttls()
            server.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
            server.sendmail(cfg["ALERT_EMAIL_FROM"], [cfg["ALERT_EMAIL_TO"]], message.as_string())
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailSendError(f"Failed to send email: {exc}") from exc

    return f"Email alert sent to {cfg['ALERT_EMAIL_TO']}."


mcp = FastMCP("email-alerts")


@mcp.tool()
def send_email_alert(subject: str, body: str) -> str:
    """Send an email alert with the given subject and body to the pre-configured operator address."""
    try:
        return send_email(subject, body)
    except EmailSendError as exc:
        raise RuntimeError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run()
