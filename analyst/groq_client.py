"""Free hosted LLM backend via Groq, shaped to look like the Anthropic client.

WHY this exists alongside ollama_client:
    Ollama is free but LOCAL — it can't run on a public cloud deploy. Groq is a
    free, hosted, OpenAI-compatible inference API, so it's the "free" backend
    that actually works in production. Like the Ollama adapter, it exposes the
    exact `client.messages.create(...)` shape the agents already use, so setting
    LLM_PROVIDER=groq runs the identical two-agent pipeline with no other change.

JSON handling:
    Groq speaks the OpenAI Chat Completions API, which supports a coarse JSON
    mode (`response_format={"type": "json_object"}`) rather than full JSON-schema
    constraint. We enable JSON mode whenever the caller asked for structured
    output; the shared llm_json helper's parse-and-retry then covers the residual
    "valid JSON but wrong keys" cases, exactly as it does for Claude.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from types import SimpleNamespace

from . import config


class GroqError(OSError):
    """Raised when Groq can't be reached, is unauthorized, or errors out.

    Subclasses OSError so the shared llm_json helper catches it in the same net
    as an anthropic APIError and wraps it in a clean ClaudeJSONError.
    """


class _Messages:
    def __init__(self, base: str, model: str, api_key: str, timeout: float):
        self._base = base
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def create(
        self,
        *,
        model: str,  # ignored: we use the configured Groq model, not Claude's id
        max_tokens: int,
        system: str,
        messages: list[dict],
        output_config: dict | None = None,
        **_: object,
    ):
        """Mimic anthropic Messages.create against Groq's OpenAI-compatible API."""
        system_content = system
        response_format = None
        if output_config:  # caller wants JSON — turn on Groq's JSON mode
            response_format = {"type": "json_object"}
            # Groq/OpenAI JSON mode rejects the request (400) unless the word
            # "json" appears somewhere in the messages. Our schema-driven prompts
            # don't always say it, so guarantee it in the system message.
            if "json" not in system_content.lower():
                system_content += "\n\nRespond with a single valid JSON object."

        payload: dict = {
            "model": self._model,
            "messages": [{"role": "system", "content": system_content}, *messages],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        if response_format:
            payload["response_format"] = response_format

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                # Groq sits behind Cloudflare, which blocks the default
                # "Python-urllib/x.y" agent with error 1010 ("banned browser
                # signature"). Send an explicit, ordinary User-Agent so the
                # request looks like a normal API client and gets through.
                "User-Agent": "autonomous-data-analyst/1.0 (+https://github.com/Purvee25/data-analyst-agent)",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise GroqError(f"Groq API error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise GroqError(f"Could not reach Groq at {self._base} ({exc}).") from exc
        except Exception as exc:  # noqa: BLE001 - surfaced as a clean provider error
            raise GroqError(f"Groq request failed: {exc}") from exc

        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GroqError(f"Unexpected Groq response shape: {body}") from exc

        block = SimpleNamespace(type="text", text=text)
        return SimpleNamespace(stop_reason="end_turn", content=[block])


class GroqClient:
    """Drop-in stand-in for anthropic.Anthropic backed by Groq's free API."""

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float | None = None):
        key = api_key or os.environ.get(config.GROQ_API_KEY_ENV)
        if not key:
            raise GroqError(
                f"{config.GROQ_API_KEY_ENV} is not set. Get a free key at "
                "https://console.groq.com and set it before making calls."
            )
        self.messages = _Messages(
            base=config.GROQ_API_BASE,
            model=model or config.GROQ_MODEL,
            api_key=key,
            timeout=timeout if timeout is not None else config.GROQ_TIMEOUT,
        )
