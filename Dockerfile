# Multi-stage build: compile the React frontend, then serve it + the FastAPI
# API from one lean Python image. The result is a SINGLE deployable service —
# the browser calls /api/* same-origin, so there is no second host and no CORS.
# Portable to Render, Railway, Fly.io, and Cloud Run (all inject $PORT).

# --- Stage 1: build the frontend -------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
# Copy manifests first so `npm ci` is cached until deps actually change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build            # -> /app/frontend/dist

# --- Stage 2: runtime ------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Python deps first (cached until requirements change).
COPY requirements.txt ./
RUN pip install -r requirements.txt

# App code + the built frontend from stage 1.
COPY analyst/ ./analyst/
COPY api/ ./api/
COPY mcp_server/ ./mcp_server/
COPY data/ ./data/
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Run as a non-root user (least privilege) and give it a writable logs dir.
RUN useradd --create-home appuser && mkdir -p /app/logs && chown -R appuser /app
USER appuser

EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8010')+'/api/health').status==200 else 1)"

# Hosts inject $PORT; default to 8010 for local `docker run`.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8010}"]
