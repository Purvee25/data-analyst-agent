# Deploying the Autonomous Data Analyst

The app ships as a **single Docker service**: the FastAPI backend serves both the
JSON API and the built React frontend, so there's one URL, no CORS, and no second
host to manage. A public server can't reach a local Ollama, so the deployed app
runs on **Groq** — a free, hosted, OpenAI-compatible model.

## 1. Get a free Groq API key

1. Go to <https://console.groq.com> and sign in (free, no card).
2. **API Keys → Create API Key**, copy it (starts with `gsk_…`).

You'll paste this into the host in step 2 — never commit it to git.

## 2. Deploy to Render (free, one-click Blueprint)

The repo already contains [`render.yaml`](render.yaml) and a [`Dockerfile`](Dockerfile).

1. Go to <https://dashboard.render.com> → **New → Blueprint**.
2. Connect the GitHub repo `Purvee25/data-analyst-agent` and select the `main` branch.
3. Render reads `render.yaml` and proposes one web service. Click **Apply**.
4. When prompted for the `GROQ_API_KEY` env var (it's marked "sync: false"),
   paste your Groq key. Leave `LLM_PROVIDER=groq` as-is.
5. First build takes a few minutes (it builds the frontend, then the Python image).
   When it goes **Live**, open the URL — that's your public app.

> **Free-tier note:** the service spins down after ~15 min idle, so the first
> request after a nap has a cold-start delay (~30 s). That's normal for free Render.

### Optional: enable the "Email this insight" action
Add these env vars in the Render dashboard (Environment tab):
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `ALERT_EMAIL_FROM`,
`ALERT_EMAIL_TO`. Without them the button is disabled with a clear hint.

## 3. Verify

- `https://<your-app>.onrender.com/api/health` → `{"status":"ok","provider":"groq","ready":true,…}`
- Open the root URL, click **Try the Superstore demo → Generate insights**.

## Run the container locally (optional)

```bash
docker build -t data-analyst .
docker run -p 8010:8010 -e LLM_PROVIDER=groq -e GROQ_API_KEY=gsk_... data-analyst
# open http://localhost:8010
```

## Switching the model / provider

Everything is env-driven — no code change:

| Goal | Env vars |
|------|----------|
| Free hosted (default deploy) | `LLM_PROVIDER=groq`, `GROQ_API_KEY=gsk_…` (opt: `GROQ_MODEL`) |
| Paid, best quality | `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=sk-ant-…` |
| Free local (dev only) | `LLM_PROVIDER=ollama`, `OLLAMA_MODEL=qwen2.5-coder:7b` |

## Other hosts

The `Dockerfile` is portable. **Railway:** New Project → Deploy from repo (auto-detects
the Dockerfile) → set `LLM_PROVIDER` + `GROQ_API_KEY`. **Fly.io:** `fly launch` (it
reads the Dockerfile) → `fly secrets set GROQ_API_KEY=…`. **Cloud Run:** `gcloud run
deploy --source .` → set the same env vars. All inject `$PORT`, which the image honors.
