"""Free local-LLM backend via Ollama, shaped to look like the Anthropic client.

WHY an adapter instead of rewriting the agents:
    The insight/critic/Q&A agents all talk to `client.messages.create(...)` and
    read `response.stop_reason` / `response.content[i].text` (see llm_json.py).
    Rather than fork that logic per provider, this module exposes an object with
    the *same shape*, backed by a local Ollama model. Set LLM_PROVIDER=ollama and
    every agent runs unchanged — for free, offline, with no API key or credits.

    This is a substitute for the paid Anthropic API when credits aren't
    available. Quality is lower than Claude (these are 2-7B local models), but the
    full pipeline — two independent calls, JSON schema, critic verdicts, charts —
    runs identically end to end.

Ollama's native /api/chat endpoint supports structured outputs: pass a JSON
schema as `format` and the model is constrained to emit matching JSON. We map
Anthropic's output_config.format.schema straight onto it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from types import SimpleNamespace

from . import config


class OllamaError(OSError):
    """Raised when the local Ollama server can't be reached or errors out.

    Subclasses OSError (as urllib's URLError does) so the shared llm_json helper
    catches it with the same net as an anthropic APIError and wraps it in a
    clean ClaudeJSONError — no provider-specific handling needed downstream.
    """


class _Messages:
    def __init__(self, host: str, model: str, timeout: float):
        self._host = host
        self._model = model
        self._timeout = timeout

    def create(
        self,
        *,
        model: str,  # ignored: we use the configured Ollama model, not Claude's id
        max_tokens: int,
        system: str,
        messages: list[dict],
        output_config: dict | None = None,
        **_: object,
    ):
        """Mimic anthropic Messages.create against a local Ollama model.

        Returns an object with `.stop_reason` and `.content` (a list of blocks
        with `.type`/`.text`) — exactly what llm_json._extract_text expects.
        """
        schema = None
        if output_config:
            schema = output_config.get("format", {}).get("schema")

        payload: dict = {
            "model": self._model,
            "stream": False,
            # Prepend the system prompt as a system message; Ollama supports it.
            "messages": [{"role": "system", "content": system}, *messages],
            "options": {"num_predict": max_tokens, "temperature": 0},
        }
        if schema is not None:
            payload["format"] = schema  # constrain output to the JSON schema

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaError(
                f"Could not reach Ollama at {self._host}. Is it running "
                f"(`ollama serve`) and is the model '{self._model}' pulled? ({exc})"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - surfaced as a clean provider error
            raise OllamaError(f"Ollama request failed: {exc}") from exc

        text = (body.get("message") or {}).get("content", "")
        # Anthropic-shaped response: one text block, natural stop.
        block = SimpleNamespace(type="text", text=text)
        return SimpleNamespace(stop_reason="end_turn", content=[block])


class OllamaClient:
    """Drop-in stand-in for anthropic.Anthropic used by the agents."""

    def __init__(self, host: str | None = None, model: str | None = None, timeout: float | None = None):
        self.messages = _Messages(
            host=host or config.OLLAMA_HOST,
            model=model or config.OLLAMA_MODEL,
            timeout=timeout if timeout is not None else config.OLLAMA_TIMEOUT,
        )
