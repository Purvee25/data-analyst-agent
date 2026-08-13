# Autonomous Data Analyst Agent

An AI app that behaves like a junior data analyst. Give it a real, messy CSV and it
**cleans the data**, **proactively finds patterns**, **critiques its own findings for
statistical validity** with a second independent model call, and **answers
natural-language follow-up questions** with session memory and auto-generated charts.

Runs on **Claude** — or, with one env var, entirely **free on a local model via
Ollama** (no API key, no credits). The full two-agent pipeline is identical either way.

> **Two ways to run the UI:** a modern **React + FastAPI** web app (recommended) and
> a legacy single-file **Streamlit** app. Both drive the exact same `analyst/`
> pipeline — the difference is only the presentation layer.

## What makes it different

1. **Proactive insight discovery** — most AI data tools wait for a question. This
   agent investigates the dataset unprompted and surfaces 3–5 candidate insights
   as structured JSON (model call #1).
2. **Critic-agent self-validation** — a *second, independent* model call reviews
   each candidate for sample size, correlation-vs-causation, cherry-picked
   timeframes, and whether the cited numbers actually appear in the data. Weak
   claims are downgraded or rejected **before you see them** (model call #2). Each
   surviving insight carries a confidence score and the critic's reasoning.
3. **Free local mode** — set `LLM_PROVIDER=ollama` and every call routes through a
   local model instead of the paid API, via a drop-in adapter
   (`analyst/ollama_client.py`) shaped exactly like the Anthropic client. The UI
   reports which engine is live (`/api/health`) so it never falsely claims
   "Powered by Claude" on a local run.
4. **Built-in observability** — every request is logged to a structured CSV
   (timestamp, action, success, latency, confidence). `/api/metrics` aggregates it
   into a live panel: success rate, average latency, and the confidence trend.
5. **Real-world action via MCP, human-confirmed** — next to any critic-approved
   insight, an **"Email this insight"** button sends it through a local Model
   Context Protocol server. Nothing fires without an explicit confirm click, and
   the destination address is server-side config the model can never see or change.

## Architecture

```
Raw CSV
   │  guardrails.py ── size / row / extension validation (rejected before parsing)
   │  cleaning.py ──── code-based cleaning (dates, currency text, duplicates,
   │                   encoding fallback) + auditable DataQualityReport
   ▼
Clean DataFrame ──► insight_agent.build_data_summary()  (compact stats, never raw rows)
   │                        │
   │              ┌─────────▼──────────┐
   │              │ pipeline.py        │
   │              │  1. insight_agent  │── model call #1: 3–5 candidate insights (JSON schema)
   │              │  2. critic_agent   │── model call #2: approve / downgrade / reject + reasoning
   │              │  3. merge + log    │
   │              └─────────┬──────────┘
   │                        ▼  final insights (confidence + critic reasoning)
   │
   ├──► qa_agent.py ── NL follow-ups with trimmed session memory; emits a
   │                   declarative chart SPEC (never code) ─► charts computed by our pandas code
   │
   ├──► actions.py ── email-alert SPEC ─► guardrails.validate_action_spec ─►
   │                  human confirm ─► mcp_client.py ─► local MCP server ─► SMTP
   │
   └──► logger.py ── logs/requests.csv ─► /api/metrics ─► "Agent metrics" panel

claude_client.get_client()  ── one switch: paid Anthropic API  ⇄  free local Ollama
```

**Key design decision:** the model never sees the full dataset and never supplies
executable code. It receives a compact statistical summary (a few hundred tokens
regardless of file size) and returns schema-constrained JSON. Aggregations and
charts are computed by pandas from the real data — the model decides *what* is
worth showing, never *how* it is computed.

## Run the web app (recommended)

FastAPI backend (port 8010) + React/Vite frontend (port 5173).

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

**On Claude** (needs an API key):

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # or put it in a .env file (auto-loaded)
./run_webapp.sh
```

**Free — on a local model** (no key, no credits):

```bash
ollama pull qwen2.5-coder:7b             # one time; strong at schema-valid JSON
ollama serve                             # if not already running
LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5-coder:7b ./run_webapp.sh
```

Then open **http://localhost:5173**. Local models are slower (~30–90 s per call),
so the live streaming timeline is especially useful — you watch each stage complete.
See [WEBAPP.md](WEBAPP.md) for details and provider options.

## Deploy (free, public URL)

The app ships as a single Docker service (FastAPI serves the built React app). A
public host can't reach a local Ollama, so the deploy runs on **Groq** — a free,
hosted, OpenAI-compatible model. One-click Render blueprint + step-by-step guide
in **[DEPLOY.md](DEPLOY.md)**.

## Run the Streamlit app (legacy / alternative)

A single-file UI over the same pipeline:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

The email-alert action is optional — without `SMTP_*` / `ALERT_EMAIL_*` env vars,
everything else works and the email button fails with a clean message.

## Tests

95 unit + HTTP-contract tests, fully mocked — no network, no API key, no SMTP:

```bash
pytest
```

Coverage spans cleaning, guardrails, both agents, the QA agent, the pipeline,
the FastAPI endpoints (health, metrics, rate limiting, the email action), the
Ollama adapter, the logger, and provider selection. CI runs them on every push
([.github/workflows/ci.yml](.github/workflows/ci.yml)).

Live smoke tests that make real, billed calls:

```bash
python scripts/check_insights.py data/superstore.csv   # real insight run
python scripts/check_email_alert.py                    # sends a real email
```

## Production hardening

| Requirement | Where |
|---|---|
| Error handling — no raw tracebacks | every agent wraps failures in one domain exception; API/UI catch and show clean messages |
| Input validation — 5 MB / 50k rows / .csv only | `guardrails.validate_upload`, `validate_row_count` |
| Destructive-op blocking | `guardrails.is_destructive` + whitelisted chart/action specs |
| Human-in-the-loop for real-world actions | explicit confirm step before any MCP action executes |
| Rate limiting — 15 AI requests / session | per-session counter (`api/main.py`, `app.py`) |
| CORS allowlist | `api/main.py` (local dev origins by default; `CORS_ALLOW_ORIGINS` to override) |
| Structured logging + live metrics | `logger.py` → `logs/requests.csv` → `/api/metrics` |
| Secrets via env / secrets manager | key read from env, never in source (`.env` gitignored) |
| Unit + HTTP tests (95, fully mocked) | `tests/` |
| CI on every push | `.github/workflows/ci.yml` |

## Dataset

Kaggle **Superstore Sales** (`data/superstore.csv`): ~9,994 retail transactions with
genuine messiness — Windows-1252 encoding (handled by fallback), text-format M/D/Y
dates, negative profits from discounting, embedded commas in product names.

## Known limitations (own them in interviews)

- **Local-model quality is lower than Claude.** The free path runs small 2–7B
  models; insights are simpler and occasionally less precise. Nothing is faked — it
  is a real (weaker) LLM running the identical pipeline.
- **The critic is AI-judged, not a formal statistical test.** It reliably catches
  the common failure classes (tiny samples, causal overreach, invented numbers),
  validated by manual spot-checking — it is not a mathematically rigorous audit.
- **One real-world action so far.** Email via MCP is wired up; the
  `actions.py` / `validate_action_spec` pattern is built to extend (Slack, tickets),
  but only email exists today.
- **Single-instance server state.** Sessions live in an in-memory dict — fine for
  one process; a multi-worker deploy would need a shared store (e.g. Redis).
- **No external context.** Insights come from the uploaded data only; it won't know
  a sales dip coincided with a holiday unless a search tool is added.
