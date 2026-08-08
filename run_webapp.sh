#!/usr/bin/env bash
# Start the React web app: FastAPI backend (port 8010) + Vite frontend (port 5173).
#
# Usage (paid Claude API):
#   export ANTHROPIC_API_KEY=sk-ant-...     # or put it in a .env file (auto-loaded)
#   ./run_webapp.sh
#
# Usage (FREE local model via Ollama — no API key or credits needed):
#   ollama serve                            # if not already running
#   LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.2 ./run_webapp.sh
#
# Then open http://localhost:5173 in your browser. Ctrl-C stops both servers.
set -euo pipefail
cd "$(dirname "$0")"

# Load .env if present (so ANTHROPIC_API_KEY is available to the backend).
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

BACKEND_PORT="${BACKEND_PORT:-8010}"

echo "→ Starting FastAPI backend on http://localhost:${BACKEND_PORT}"
python3 -m uvicorn api.main:app --host 127.0.0.1 --port "${BACKEND_PORT}" &
BACKEND_PID=$!

echo "→ Starting Vite frontend on http://localhost:5173"
( cd frontend && npm run dev ) &
FRONTEND_PID=$!

# Stop both servers on Ctrl-C / exit.
trap 'echo; echo "Stopping…"; kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true' INT TERM EXIT

echo
echo "Open  http://localhost:5173  in your browser."
wait
