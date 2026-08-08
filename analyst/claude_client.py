"""Shared Claude API client construction.

WHY this is its own module instead of living inside insight_agent.py:
    Phase 3 adds a critic agent that makes a SECOND, independent Claude API call.
    Both agents need identical, correct client construction (same env var, same
    error message when the key is missing) — duplicating that logic invites the
    two copies to drift. A one-line shared helper keeps "how do we authenticate"
    in exactly one place.

WHY we read the key from an environment variable rather than accepting it as a
plain function argument with a default of None that falls through to hardcoding:
    Production requirement (secrets management) — the key must never appear in
    source. Constructing the client with no explicit api_key= lets the SDK's own
    resolution order do the work (env var, then other credential sources), and we
    only add a clearer error message on top for the common "forgot to set it" case.
"""

from __future__ import annotations

import os

import anthropic

from . import config


class ClaudeConfigError(Exception):
    """Raised when the Claude API client cannot be constructed (e.g. missing key)."""


def get_client() -> anthropic.Anthropic:
    """Build an Anthropic client, failing fast with a clear message if unconfigured.

    We check for the env var explicitly (rather than letting a bare `Anthropic()`
    raise deep inside the SDK) so callers — and the Streamlit UI in a later phase —
    get a message that names the exact env var to set, not a generic auth error.
    """
    # Free local substitute: route every agent call through Ollama instead of
    # the paid API. Selected with LLM_PROVIDER=ollama; needs no API key.
    if config.LLM_PROVIDER == "ollama":
        from .ollama_client import OllamaClient

        return OllamaClient()

    if config.API_KEY_ENV_VAR not in os.environ:
        raise ClaudeConfigError(
            f"{config.API_KEY_ENV_VAR} is not set. Set it in your environment "
            "(or in Streamlit secrets when deployed) before making API calls."
        )
    return anthropic.Anthropic()
