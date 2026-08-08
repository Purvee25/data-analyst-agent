"""Thin synchronous wrapper around the MCP stdio client for local tool calls.

WHY spawn a fresh server subprocess per call instead of keeping one alive:
    Actions here (email alerts) are rare, human-confirmed, one-off events —
    not a hot path like the Claude calls. A fresh stdio subprocess per call
    keeps the client dead simple (no long-lived process to manage across
    Streamlit reruns, which tear down and rebuild script-level state on every
    interaction) at a startup cost of well under a second.

WHY asyncio.run here even though the rest of the app is synchronous:
    The official `mcp` SDK is async-only. This module is the single place
    that bridges into asyncio so nothing else in the codebase needs to know
    the MCP client is async under the hood.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import config

_SERVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mcp_server",
    "email_alert_server.py",
)


class MCPClientError(Exception):
    """Raised when an MCP tool call cannot connect, times out, or errors."""


async def _call_tool_async(tool_name: str, arguments: dict[str, Any], timeout: float) -> str:
    # WHY env=dict(os.environ) is required here:
    #   StdioServerParameters defaults to mcp's get_default_environment(), which
    #   forwards only a small safe subset (PATH, HOME, etc.) and deliberately
    #   drops everything else — SMTP_*, SLACK_WEBHOOK_URL, TICKET_WEBHOOK_URL
    #   would silently never reach the server otherwise, surfacing as a
    #   confusing "missing config" error even when .env is set correctly.
    server_params = StdioServerParameters(
        command=sys.executable, args=[_SERVER_SCRIPT], env=dict(os.environ)
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=timeout)
            result = await asyncio.wait_for(session.call_tool(tool_name, arguments), timeout=timeout)

    if result.isError:
        detail = result.content[0].text if result.content else "unknown MCP tool error"
        raise MCPClientError(detail)
    return result.content[0].text if result.content else "OK"


def call_tool(
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = config.MCP_CALL_TIMEOUT_SECONDS,
) -> str:
    """Call a tool on the local email-alert MCP server and return its text result.

    Raises MCPClientError for connection failures, timeouts, or a tool-side
    error (e.g. missing SMTP config) — callers never need to distinguish
    these cases, only show str(exc).
    """
    try:
        return asyncio.run(_call_tool_async(tool_name, arguments, timeout))
    except asyncio.TimeoutError as exc:
        raise MCPClientError(f"MCP tool call timed out after {timeout}s.") from exc
    except MCPClientError:
        raise
    except Exception as exc:  # subprocess spawn failures, protocol errors, etc.
        raise MCPClientError(f"MCP tool call failed: {exc}") from exc
