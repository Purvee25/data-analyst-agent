"""Tests for config.provider_info() — the source of truth the UI trusts.

The frontend badge/footer render whatever this returns, so an inaccurate label
here becomes a user-facing "Powered by Claude" lie on a free local run. These
tests pin the contract for both backends.
"""

from __future__ import annotations

from analyst import config


def test_provider_info_anthropic(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "CLAUDE_MODEL", "claude-opus-4-8")
    info = config.provider_info()
    assert info["provider"] == "anthropic"
    assert info["is_local"] is False
    assert info["model"] == "claude-opus-4-8"
    assert info["label"] == "Powered by Claude"
    assert info["call_noun"] == "Claude call"


def test_provider_info_ollama_reports_free_local(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(config, "OLLAMA_MODEL", "qwen2.5-coder:7b")
    info = config.provider_info()
    assert info["provider"] == "ollama"
    assert info["is_local"] is True
    # Must surface the local model, never the Claude id.
    assert info["model"] == "qwen2.5-coder:7b"
    assert "free" in info["label"].lower()
    assert "Claude" not in info["call_noun"]
    assert "qwen2.5-coder:7b" in info["engine_label"]
