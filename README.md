# Autonomous Data Analyst Agent

A Python application that behaves like a junior data analyst: give it a real, messy
CSV and it **proactively finds patterns**, **critiques its own findings for
statistical validity** with a second independent AI call, and **answers
natural-language follow-up questions** with session memory and auto-generated charts.

Two front ends share the same `analyst/` core:
- **React + FastAPI web app** (recommended) — a live, streaming dashboard where you
  watch the two agents work in real time. See [WEBAPP.md](WEBAPP.md).
- **Streamlit app** (`app.py`) — the original single-file UI.

**Runs for free.** The LLM backend is pluggable: use the paid Claude API, or set
`LLM_PROVIDER=ollama` to run the *entire* pipeline on a **free local model** (via
[Ollama](https://ollama.com)) with no API key or credits. Same agents, same JSON
schema, same critic — just a local model. The UI labels which engine is active so
"Powered by Claude" is never a false claim.

## What makes it different

1. **Proactive insight discovery** — most AI data tools wait for a question. This
   agent investigates the dataset unprompted and surfaces 3–5 candidate insights
   as structured JSON (Claude call #1).
2. **Critic-agent self-validation** — a *second, independent* Claude call reviews
   each candidate for sample size, correlation-vs-causation, cherry-picked
   timeframes, and whether the cited numbers actually appear in the data. Weak
   claims are downgraded or rejected **before** you ever see them (Claude call #2).
3. **Built-in observability** — every request is logged to a structured CSV
   (timestamp, action, success, latency, confidence), and that log powers a live
   *Agent metrics* panel in the UI: success rate, average latency, and the
   confidence trend across insights. Logging isn't an afterthought — it's the
   basis for a real accuracy metric.
4. **Real-world action via MCP, human-confirmed** — the agent isn't read-only
   anymore: next to any critic-approved insight, a **"Email this insight"**
   button sends it as a real email through a local Model Context Protocol
   server. Nothing fires without an explicit confirm click, and the
   destination address is operator config the agent can never see or change
   — the model may only influence subject/body text.

## Architecture

```
Raw CSV
   ↓  guardrails.py ── size / row / extension validation (rejected before parsing)
   ↓  cleaning.py ──── code-based cleaning (dates, currency text, duplicates,
   │                   encoding fallback) + auditable DataQualityReport
   ↓
Clean DataFrame ──► insight_agent.build_data_summary()   (compact stats, never raw rows)
   │                        │
   │              ┌─────────▼──────────┐
   │              │ pipeline.py        │
   │              │  1. insight_agent  │── Claude call #1: 3–5 candidate insights (JSON schema)
   │              │  2. critic_agent   │── Claude call #2: approve / downgrade / reject + reasoning
   │              │  3. merge + log    │
   │              └─────────┬──────────┘
   │                        ▼
   │              Final insights (confidence + critic reasoning)
   │
   ├──► qa_agent.py ── NL follow-ups with trimmed session memory; emits a
   │                   declarative chart SPEC (never code)
   │        ↓
   │    guardrails.validate_chart_spec ──► charts.py (pandas groupby + matplotlib —
   │                                       every plotted number computed by our code)
   │
   ├──► actions.py ── declarative email-alert action SPEC (never code)
   │        ↓
   │    guardrails.validate_action_spec ──► app.py human confirm click ──►
   │    mcp_client.py (spawns mcp_server/email_alert_server.py over stdio) ──►
   │    real SMTP send. Recipient is server-side config, never model output.
   │
   └──► logger.py ── logs/requests.csv ──► "Agent metrics" panel (USP #3)

app.py (Streamlit) — thin UI layer: session state, per-session rate limit (15
billable requests), and try/except around every external call.
```

**Key design decision:** the model never sees the full dataset and never supplies
executable code. It receives a compact statistical summary (a few hundred tokens
regardless of file size) and returns schema-constrained JSON. Aggregations and
charts are computed by pandas from the real data — the model decides *what* is
worth showing, never *how* it is computed.

## Production hardening

| Requirement | Where |
|---|---|
| Error handling — no raw tracebacks | every agent wraps failures in one domain exception; `app.py` catches and shows clean messages |
| Input validation — 5 MB / 50k rows / .csv only | `guardrails.validate_upload`, `validate_row_count` |
| Destructive-op blocking | `guardrails.is_destructive` + whitelisted chart/action specs |
| Human-in-the-loop for real-world actions | `app.py` explicit confirm/cancel step before any MCP action executes |
| Rate limiting — 15 requests/session | `app.py` session-state counter |
| Structured logging | `logger.py` → `logs/requests.csv` → metrics panel |
| Secrets via env / Streamlit secrets | `claude_client.py`; key never in source (`.env` gitignored) |
| Unit tests (80, fully mocked — zero network) | `tests/` |
| CI on every push | `.github/workflows/ci.yml` |

## Run locally

**Web app (React + FastAPI) — recommended.** Free local mode, no API key:

```bash
pip install -r requirements.txt
ollama pull qwen2.5-coder:7b && ollama serve      # free local model
LLM_PROVIDER=ollama ./run_webapp.sh               # → http://localhost:5173
```

Or with the paid Claude API — drop `LLM_PROVIDER=ollama` and set `ANTHROPIC_API_KEY`
first. Full details, including the metrics panel and email action, are in
[WEBAPP.md](WEBAPP.md).

**Streamlit app** (original single-file UI):

```bash
pip install -r requirements.txt
cp .env.example .env           # paste your ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)
streamlit run app.py
```

The email-alert action is optional — without `SMTP_*` / `ALERT_EMAIL_*` env
vars set, everything else works normally and clicking "Email this insight"
just fails with a clean "missing SMTP env var" message instead of a crash.

Run the tests (no API key or SMTP needed — all Claude calls and MCP tool
calls are mocked):

```bash
pytest
```

Manual live smoke test of the insight agent (makes real, billed API calls):

```bash
python scripts/check_insights.py data/superstore.csv
```

Manual live smoke test of the email-alert MCP action (sends a real email):

```bash
python scripts/check_email_alert.py
```

## Deploy (Streamlit Community Cloud — free)

1. Push this repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), create an app pointing at `app.py`.
3. In the app's **Secrets** settings add: `ANTHROPIC_API_KEY = "sk-ant-..."`.
4. (Optional) Add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
   `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` to enable the "Email this insight" action.
5. Done — public URL.

## Dataset

Kaggle **Superstore Sales** (`data/superstore.csv`): ~9,994 retail transactions with
genuine messiness — Windows-1252 encoding (handled by fallback), text-format M/D/Y
dates, negative profits from discounting, embedded commas in product names.

## Known limitations (asked about these in interviews? own them)

- **One real-world action so far.** The agent can now send an email alert via
  a local MCP server, but that's it — no tickets, no Slack, no CRM writes.
  The `actions.py` / `guardrails.validate_action_spec` pattern is built to
  extend (add a new `ALLOWED_ACTIONS` entry + executor branch + MCP tool),
  but only email is wired up today.
- **The critic is AI-judged, not a formal statistical test.** It reliably catches
  the common failure classes (tiny samples, causal overreach, invented numbers),
  validated by manual spot-checking — it is not a mathematically rigorous audit.
- **No external context.** Insights come from the uploaded data's schema and
  statistics only; it won't know a sales dip coincided with a holiday unless a
  search tool is added.
