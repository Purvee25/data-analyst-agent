"""Local MCP server exposing three outbound-alert tools: send_email_alert,
send_slack_alert, create_ticket.

Spawned as a subprocess over stdio by analyst/mcp_client.py — this is the
Model Context Protocol's standard local-tool transport. Can also be run
standalone for manual testing:

    python -m mcp_server.alerts_server

WHY destinations (recipient email, Slack webhook, ticket webhook) are read
from THIS process's own environment instead of being accepted as tool
arguments:
    subject/body/title/description are the only inputs a caller (ultimately,
    an LLM-influenced insight) can supply. If the destination were also an
    argument, a prompt-injected insight could redirect an alert to an
    attacker-controlled address or endpoint. The destination is operator
    config, not agent output — same trust boundary the chart-spec whitelist
    in guardrails.py enforces for chart requests.

WHY the send/create functions are plain functions separate from the
@mcp.tool wrappers:
    Each has no MCP/asyncio dependency, so it's testable with a one-line mock
    of smtplib.SMTP or requests.post instead of spinning up the MCP protocol
    machinery.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

import requests
from mcp.server.fastmcp import FastMCP

# --- Email -------------------------------------------------------------------

EMAIL_REQUIRED_ENV_VARS = (
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
    missing = [name for name in EMAIL_REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise EmailSendError(
            f"Missing required SMTP env var(s): {', '.join(missing)}. "
            "Set them before running the alerts MCP server."
        )
    return {name: os.environ[name] for name in EMAIL_REQUIRED_ENV_VARS}


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


# --- Slack ---------------------------------------------------------------------


class SlackSendError(Exception):
    """Raised when the Slack webhook URL is missing or the post fails."""


def send_slack_message(text: str, http_post=requests.post) -> str:
    """POST a message to a Slack Incoming Webhook. Returns a confirmation string."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise SlackSendError(
            "Missing required env var: SLACK_WEBHOOK_URL. "
            "Set it before running the alerts MCP server."
        )
    try:
        response = http_post(webhook_url, json={"text": text}, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SlackSendError(f"Failed to post Slack message: {exc}") from exc

    return "Slack alert posted."


# --- Ticket (generic webhook) ---------------------------------------------------


class TicketCreateError(Exception):
    """Raised when the ticket webhook URL is missing or the request fails."""


def create_ticket_via_webhook(title: str, description: str, http_post=requests.post) -> str:
    """POST a ticket payload to a generic webhook (Jira/Linear/Asana automation, etc.)."""
    webhook_url = os.environ.get("TICKET_WEBHOOK_URL")
    if not webhook_url:
        raise TicketCreateError(
            "Missing required env var: TICKET_WEBHOOK_URL. "
            "Set it before running the alerts MCP server."
        )
    try:
        response = http_post(
            webhook_url, json={"title": title, "description": description}, timeout=15
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise TicketCreateError(f"Failed to create ticket: {exc}") from exc

    return "Ticket created."


# --- MCP tool wrappers -----------------------------------------------------------

mcp = FastMCP("agent-alerts")


@mcp.tool()
def send_email_alert(subject: str, body: str) -> str:
    """Send an email alert with the given subject and body to the pre-configured operator address."""
    try:
        return send_email(subject, body)
    except EmailSendError as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
def send_slack_alert(text: str) -> str:
    """Post an alert message to the pre-configured Slack channel via Incoming Webhook."""
    try:
        return send_slack_message(text)
    except SlackSendError as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
def create_ticket(title: str, description: str) -> str:
    """Create a ticket with the given title and description via the pre-configured webhook."""
    try:
        return create_ticket_via_webhook(title, description)
    except TicketCreateError as exc:
        raise RuntimeError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run()
