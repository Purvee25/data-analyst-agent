"""Central configuration for the Autonomous Data Analyst Agent.

WHY a single config module:
    Every production-hardening limit (upload size, row cap, rate limit) and every
    "magic number" the app depends on lives here in ONE place. In interviews and in
    ops, "where do I change the API cost ceiling?" should have a single, obvious
    answer. Scattering these constants across app.py / agents / guardrails is how
    limits silently drift out of sync.

Nothing in this module imports pandas, Streamlit, or the Anthropic SDK, so it is
safe to import from tests and from any layer without side effects.
"""

from __future__ import annotations

import os

# --- Model configuration ---------------------------------------------------
# We pin a single, current Claude model id here. Both the insight agent and the
# critic agent read from this so they stay on the same model unless we
# deliberately diverge them. Override via the CLAUDE_MODEL env var (e.g. to
# "claude-sonnet-5") if lower per-request cost matters more than quality for
# your deployment — the rate limiter (MAX_REQUESTS_PER_SESSION) is the primary
# cost control either way.
CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

# --- LLM provider selection ------------------------------------------------
# "anthropic" (default) uses the paid Claude API. "ollama" runs a FREE local
# model via Ollama (http://localhost:11434) — a no-credit substitute so the
# whole pipeline works offline. Both go through the same agent code; only the
# client construction differs (see claude_client.get_client()).
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "anthropic").lower()
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Local model tag. qwen2.5-coder:7b is the default — noticeably stronger at
# emitting schema-valid JSON than the smaller llama3.2 (which is faster but
# looser). Override with OLLAMA_MODEL to trade quality for speed.
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
# Local models are slower than the API — give them room (seconds).
OLLAMA_TIMEOUT: float = float(os.environ.get("OLLAMA_TIMEOUT", "180"))


def provider_info() -> dict:
    """Describe the LLM backend the pipeline is actually using right now.

    The UI reads this (via /api/health) so the badge and footer tell the truth:
    "Powered by Claude" vs "Running free on a local model". Hardcoding "Claude"
    in the frontend would misrepresent an Ollama run — an honesty bug worth
    avoiding, especially when the whole point of the local path is that it's free.
    """
    is_local = LLM_PROVIDER == "ollama"
    model = OLLAMA_MODEL if is_local else CLAUDE_MODEL
    return {
        "provider": LLM_PROVIDER,
        "model": model,
        "is_local": is_local,
        # Short human labels the frontend can show verbatim.
        "label": "Running free on a local model" if is_local else "Powered by Claude",
        "engine_label": f"{model} · local & free" if is_local else f"Claude · {model}",
        # Per-call vocabulary that adapts feature copy ("Claude call #1" is wrong
        # when the call is going to a local model).
        "call_noun": "local model call" if is_local else "Claude call",
    }

# Separate, smaller token budgets per call keep latency and cost predictable.
INSIGHT_MAX_TOKENS: int = 2000
CRITIC_MAX_TOKENS: int = 1500
QA_MAX_TOKENS: int = 1500

# Cap on stored Q&A conversation turns (messages, not turns) kept in session
# memory and resent to Claude on each follow-up question. Bounds both the
# per-request token cost and memory growth over a long Q&A session.
QA_HISTORY_MAX_MESSAGES: int = 20

# --- Input validation limits (production hardening req #9) ------------------
# 5 MB matches the requirement. Streamlit also enforces a server-side upload cap,
# but we validate independently so the rule is explicit and testable.
MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5 MB
# Row cap protects both memory and the size of the data summary we send to Claude.
MAX_ROWS: int = 50_000

# --- Rate limiting (production hardening req #11) ---------------------------
# Each Streamlit session may make at most this many *billable* agent requests
# (insight generation + Q&A). Chosen to bound API spend per user session.
MAX_REQUESTS_PER_SESSION: int = 15

# --- Insight generation tuning ---------------------------------------------
# How many candidate insights we ask the insight agent to produce. The critic
# may reject some, so we ask for a few extra headroom.
INSIGHTS_TO_REQUEST: int = 5

# When we summarise the data for the LLM, cap how many sample rows we include so
# the prompt stays small and cheap. The agents see aggregate stats + a sample,
# never the full dataset.
SAMPLE_ROWS_FOR_LLM: int = 15

# --- Logging (production hardening req #12) --------------------------------
# Every request is appended here as a row for later accuracy/validity analysis.
# Default is anchored to the repo root (this file's parent's parent) so the log
# lands in the same place no matter which working directory launched the app.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR: str = os.environ.get("ANALYST_LOG_DIR", os.path.join(_REPO_ROOT, "logs"))
LOG_CSV_PATH: str = os.path.join(LOG_DIR, "requests.csv")

# --- Secrets (production hardening req #13) --------------------------------
# Name of the env var / Streamlit secret holding the API key. Never hardcode the
# key itself; only the *name* of where to find it lives in source.
API_KEY_ENV_VAR: str = "ANTHROPIC_API_KEY"

# --- MCP action integration (email alerts) ----------------------------------
# The email-alert MCP server (mcp_server/email_alert_server.py) is spawned
# locally as a subprocess over stdio, once per confirmed action — see
# analyst/mcp_client.py. SMTP credentials and the alert recipient live in the
# SERVER process's own environment, never passed through the client or model
# (see that module's docstring for why). ALERT_EMAIL_TO is read here too, but
# only to *display* the destination in the UI confirm step — the send itself
# re-reads it server-side.
MCP_CALL_TIMEOUT_SECONDS: float = 20.0
ALERT_EMAIL_TO: str = os.environ.get("ALERT_EMAIL_TO", "")
# Separate from MAX_REQUESTS_PER_SESSION (that one bounds Claude API spend);
# this bounds outbound email volume from a single session regardless of cost.
MAX_ACTIONS_PER_SESSION: int = 5
