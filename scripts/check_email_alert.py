"""Manual smoke test for the email-alert MCP action — not a pytest test.

Spawns the real email_alert_server.py over stdio (via analyst.mcp_client) and
sends a real test email through your configured SMTP account. This is a
manual review tool, mirroring scripts/check_insights.py — it intentionally
sends a real message and is never run in CI.

Usage:
    export SMTP_HOST=... SMTP_PORT=... SMTP_USERNAME=... SMTP_PASSWORD=...
    export ALERT_EMAIL_FROM=... ALERT_EMAIL_TO=...
    python scripts/check_email_alert.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyst.actions import ActionError, build_email_alert_spec, execute_action
from analyst.guardrails import ValidationError


def main() -> int:
    fake_insight = {
        "category": "Smoke Test",
        "insight": "This is a manual smoke test of the email-alert MCP action.",
        "confidence": 0.99,
        "supporting_data": "scripts/check_email_alert.py",
    }
    spec = build_email_alert_spec(fake_insight)
    print(f"Sending test email — subject: {spec['subject']!r}")

    try:
        result = execute_action(spec)
    except (ValidationError, ActionError) as exc:
        print(f"Email alert failed: {exc}")
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
