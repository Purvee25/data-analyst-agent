"""Tests for LLM client construction / provider selection (analyst/claude_client.py).

get_client() is the single switch between the paid Anthropic API and the free
local Ollama backend, and the place that fails fast with a clear message when
Claude is selected without a key.
"""

from __future__ import annotations

import pytest

from analyst import claude_client, config
from analyst.ollama_client import OllamaClient


def test_ollama_provider_returns_local_client(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    client = claude_client.get_client()
    assert isinstance(client, OllamaClient)


def test_anthropic_without_key_raises_config_error(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.delenv(config.API_KEY_ENV_VAR, raising=False)
    with pytest.raises(claude_client.ClaudeConfigError, match=config.API_KEY_ENV_VAR):
        claude_client.get_client()


def test_anthropic_with_key_builds_sdk_client(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setenv(config.API_KEY_ENV_VAR, "sk-ant-test")
    client = claude_client.get_client()
    # Duck-typed: the real SDK client exposes `.messages`.
    assert hasattr(client, "messages")
