# Web App (React + FastAPI)

A modern single-page web app that replaces the plain Streamlit UI, **reusing the
exact same `analyst/` pipeline** underneath. The Python intelligence (cleaning,
two-agent insights, critic, Q&A, guardrails, logging) is unchanged — it's just
exposed over HTTP and rendered by a React dashboard.

## Architecture

```
Browser (React + Tailwind + Recharts, port 5173)
      │  fetch /api/*  (Vite proxies to :8010 in dev)
      ▼
FastAPI backend  (api/, port 8010)
      │  calls
      ▼
analyst/  ── cleaning · insight pipeline · critic · qa · guardrails · logger
      │
      ▼
Anthropic Claude API   (two independent calls: insight-finder + critic)
```

- **`api/main.py`** — thin JSON endpoints; holds the cleaned DataFrame per session.
- **`api/chart_data.py`** — turns a validated chart spec into JSON (Recharts draws it).
- **`frontend/src/`** — React app: `Landing`, `DataQuality`, `PreviewTable`,
  `InsightsPanel` + `InsightCard`, `QAPanel` + `Chart`.

The old Streamlit app (`app.py`) still works and is kept for reference; the React
app is the primary UI.

## Run it locally

**1. Install deps (one time):**
```bash
pip install -r requirements.txt          # backend + analyst
cd frontend && npm install && cd ..       # frontend
```

**2. Set your API key** (needed only for the AI features — cleaning works without it):
```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env    # auto-loaded by run_webapp.sh
```

**3. Start both servers:**
```bash
./run_webapp.sh
```
Then open **http://localhost:5173**.

### Free local mode (no API key / no credits) — via Ollama

If you don't want to pay for the Anthropic API, run the whole pipeline on a
**free local model**. The same two-agent flow (insight-finder + critic), JSON
schema, confidence scores, and charts all work — just on a model running on your
own machine. Quality is lower than Claude, but nothing is stubbed or faked.

```bash
# one time: install a model (llama3.2 is small & fast; qwen2.5-coder:7b is better at JSON)
ollama pull llama3.2
ollama serve                     # if it isn't already running

# start the app pointed at the local model
LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.2 ./run_webapp.sh
```

Provider is chosen by env var, handled in `analyst/claude_client.get_client()`:

| Env | Effect |
|-----|--------|
| _(default)_ | Paid Anthropic API (needs `ANTHROPIC_API_KEY` + credits) |
| `LLM_PROVIDER=ollama` | Free local model via Ollama (`analyst/ollama_client.py`) |
| `OLLAMA_MODEL=<tag>` | Which local model (default `llama3.2`) |

The local model is slower (~30–90s per call), so the streaming timeline is
especially useful — you watch each stage complete live.

Or start them manually in two terminals:
```bash
# terminal 1 — backend
set -a; . ./.env; set +a
python3 -m uvicorn api.main:app --port 8010

# terminal 2 — frontend
cd frontend && npm run dev
```

## API endpoints

| Method | Path                  | Purpose                                   |
|--------|-----------------------|-------------------------------------------|
| GET    | `/api/health`         | Liveness + whether an API key is set       |
| POST   | `/api/session/demo`   | Load & clean the bundled Superstore CSV    |
| POST   | `/api/session/upload` | Validate & clean an uploaded CSV           |
| POST   | `/api/insights`       | Run generate → critique → merge pipeline   |
| POST   | `/api/ask`            | Answer one follow-up question (+ chart)    |

Every endpoint returns a clean JSON `{"detail": "..."}` on failure — a missing
API key, empty credit balance, oversized upload, or rate-limit hit shows as a
friendly banner in the UI, never a traceback.

## Build for production
```bash
cd frontend && npm run build        # outputs frontend/dist/
```
Serve `frontend/dist/` as static files behind the FastAPI app (or any static
host), pointing `/api` at the backend.
