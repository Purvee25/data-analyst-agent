"""FastAPI application exposing the analyst pipeline as JSON endpoints.

Endpoints (all under /api):
    POST /session/demo            -> load + clean the bundled Superstore file
    POST /session/upload          -> validate + clean an uploaded CSV
    POST /insights                -> run the two-agent insight pipeline
    POST /ask                     -> answer one follow-up question (+ chart data)
    GET  /health                  -> liveness / whether the API key is configured

WHY per-session server-side state (a dict keyed by session_id):
    The cleaned DataFrame and its precomputed summary are reused across many
    requests (insights, then several follow-up questions). Recleaning on every
    call would be wasteful, and shipping the whole frame to the browser and back
    would be worse. We keep it in memory keyed by an opaque session_id the client
    holds — the same "session-scoped, no cross-session persistence" model the
    Streamlit app had, just made explicit for a stateless HTTP client.

Every external/failable call is wrapped so the client always receives a clean
JSON error ({"detail": "..."}) with a sensible status code — never a raw
traceback. This is the same production-hardening contract as the Streamlit UI.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Iterator

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from analyst import actions, config
from analyst.cleaning import clean_csv_bytes
from analyst.claude_client import ClaudeConfigError
from analyst.critic_agent import CriticReviewError, merge_insights_with_reviews, review_insights
from analyst.guardrails import (
    ValidationError,
    validate_chart_spec,
    validate_question,
    validate_row_count,
    validate_upload,
)
from analyst.insight_agent import (
    InsightGenerationError,
    build_data_summary,
    generate_insights,
)
from analyst.logger import log_request
from analyst.pipeline import PipelineError, run_insight_pipeline
from analyst.qa_agent import QAError, answer_question
from api.chart_data import chart_data

app = FastAPI(title="Autonomous Data Analyst API")

# CORS: the Vite dev server (localhost:5173) and the built app are served from a
# different origin than this API during development. Allow local origins so the
# browser doesn't block the fetch. Tighten `allow_origins` for a real deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class _Session:
    """Holds one cleaned dataset + derived state for the life of a browser session."""

    def __init__(self, filename: str, df: pd.DataFrame, report, summary: str):
        self.filename = filename
        self.df = df
        self.report = report
        self.summary = summary
        # Rate limiting (production req #9): bound billable Claude calls per session.
        self.request_count = 0
        # Separate cap on outbound real-world actions (email sends) per session —
        # bounds side-effect volume independently of LLM spend.
        self.action_count = 0
        # Q&A memory (core feature #5): user/assistant turns resent to Claude.
        self.history: list[dict] = []


# Process-local session store. Fine for a single-instance app; swap for Redis if
# this ever runs multi-worker. Keyed by an opaque uuid handed to the client.
_SESSIONS: dict[str, _Session] = {}


def _get_session(session_id: str) -> _Session:
    session = _SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found. Load a dataset first.")
    return session


def _check_rate_limit(session: _Session) -> None:
    if session.request_count >= config.MAX_REQUESTS_PER_SESSION:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Session limit reached ({config.MAX_REQUESTS_PER_SESSION} AI requests). "
                "This cap controls API cost — start a new session to continue."
            ),
        )


def _preview(df: pd.DataFrame, n: int = 20) -> dict:
    """First n rows as JSON-safe {columns, rows}. Dates -> ISO, NaN -> null."""
    head = df.head(n).copy()
    for col in head.columns:
        if pd.api.types.is_datetime64_any_dtype(head[col]):
            head[col] = head[col].dt.strftime("%Y-%m-%d")
    head = head.where(pd.notna(head), None)
    return {"columns": list(head.columns), "rows": head.to_dict(orient="records")}


def _session_payload(session_id: str, session: _Session) -> dict:
    return {
        "session_id": session_id,
        "filename": session.filename,
        "rows": int(session.df.shape[0]),
        "cols": int(session.df.shape[1]),
        "quality": session.report.to_dict(),
        "quality_markdown": session.report.to_markdown(),
        "preview": _preview(session.df),
        "requests_used": session.request_count,
        "requests_max": config.MAX_REQUESTS_PER_SESSION,
    }


def _new_session(filename: str, raw: bytes) -> dict:
    try:
        df, report = clean_csv_bytes(raw)
    except Exception as exc:  # cleaning is defensive, but never leak a traceback
        raise HTTPException(status_code=400, detail=f"Could not read/clean the file: {exc}") from exc

    try:
        validate_row_count(df)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = build_data_summary(df)
    session_id = uuid.uuid4().hex
    _SESSIONS[session_id] = _Session(filename, df, report, summary)
    return _session_payload(session_id, _SESSIONS[session_id])


# --- Request models --------------------------------------------------------
class InsightsRequest(BaseModel):
    session_id: str


class AskRequest(BaseModel):
    session_id: str
    question: str


class EmailActionRequest(BaseModel):
    session_id: str
    # The full insight dict the user chose to email. The server rebuilds the
    # email spec from it (actions.build_email_alert_spec) and re-validates —
    # the client can't hand us a raw subject/body to send verbatim.
    insight: dict


# --- Endpoints -------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    """Liveness + the active LLM backend (so the UI can warn early and stay honest).

    `provider`/`model`/`label` let the frontend show the real engine — "Powered by
    Claude" vs "Running free on a local model" — instead of a hardcoded claim.
    """
    info = config.provider_info()
    # A local (Ollama) run needs no API key, so it's "ready" regardless; a Claude
    # run is only ready once the key is present.
    api_key_configured = config.API_KEY_ENV_VAR in os.environ
    # The email action only works if every SMTP var is set server-side; the UI
    # uses this to disable the button with an honest hint instead of failing late.
    email_env = ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
                 "ALERT_EMAIL_FROM", "ALERT_EMAIL_TO")
    return {
        "status": "ok",
        "api_key_configured": api_key_configured,
        "ready": info["is_local"] or api_key_configured,
        "email_configured": all(os.environ.get(v) for v in email_env),
        **info,
    }


@app.get("/api/metrics")
def metrics() -> dict:
    """Aggregate the structured request log into live agent-quality metrics.

    This is the API-side of the observability USP: the same logs/requests.csv the
    pipeline appends to becomes success rate, latency, and a confidence trend the
    UI can chart. A missing or malformed log yields zeros rather than an error —
    metrics are an observability read, never a reason to 500.
    """
    empty = {
        "total": 0, "success_rate": None, "avg_latency": None,
        "avg_confidence": None, "confidence_series": [],
    }
    if not os.path.exists(config.LOG_CSV_PATH):
        return empty
    try:
        log_df = pd.read_csv(config.LOG_CSV_PATH)
    except Exception:  # a truncated/half-written row must not break the panel
        return empty
    if log_df.empty:
        return empty

    total = int(len(log_df))
    success_rate = round(float(log_df["success"].mean()) * 100, 1)
    latencies = pd.to_numeric(log_df.get("response_time_seconds"), errors="coerce").dropna()
    conf = pd.to_numeric(log_df.get("confidence_score"), errors="coerce").dropna()
    return {
        "total": total,
        "success_rate": success_rate,
        "avg_latency": round(float(latencies.mean()), 2) if not latencies.empty else None,
        "avg_confidence": round(float(conf.mean()), 3) if not conf.empty else None,
        # Most recent 20 confidence scores, oldest→newest, for a sparkline.
        "confidence_series": [round(float(c), 3) for c in conf.tolist()[-20:]],
    }


@app.post("/api/session/demo")
def load_demo() -> dict:
    """Load and clean the bundled Superstore dataset."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "superstore.csv")
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="Demo dataset not found on the server.") from exc
    return _new_session("superstore.csv", raw)


@app.post("/api/session/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Validate (size/type/rows) and clean an uploaded CSV."""
    raw = await file.read()
    try:
        validate_upload(raw, file.filename or "")
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _new_session(file.filename or "uploaded.csv", raw)


@app.post("/api/insights")
def insights(req: InsightsRequest) -> dict:
    """Run the generate -> critique -> merge pipeline for the session's dataset."""
    session = _get_session(req.session_id)
    _check_rate_limit(session)
    session.request_count += 1
    try:
        results = run_insight_pipeline(session.df)
    except ClaudeConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"insights": results, "requests_used": session.request_count}


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """Answer one follow-up question, optionally returning chart data."""
    session = _get_session(req.session_id)
    try:
        validate_question(req.question)  # length + destructive-op guardrail
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _check_rate_limit(session)
    session.request_count += 1

    try:
        result = answer_question(req.question, session.summary, history=session.history)
    except ClaudeConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except QAError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Update session memory with this turn (bounded resend happens in the agent).
    session.history.append({"role": "user", "content": req.question})
    session.history.append({"role": "assistant", "content": result["answer"]})

    # If the model proposed a chart, validate the spec against the real frame and
    # compute the data ourselves — the model never supplies executable code.
    chart = None
    if result.get("chart"):
        try:
            spec = validate_chart_spec(result["chart"], session.df)
            chart = chart_data(session.df, spec)
        except ValidationError:
            chart = None  # a bad/hallucinated spec is silently dropped, not fatal

    return {
        "answer": result["answer"],
        "chart": chart,
        "requests_used": session.request_count,
    }


@app.post("/api/action/email")
def email_insight(req: EmailActionRequest) -> dict:
    """Email one critic-approved insight via the local MCP server (human-confirmed).

    This is the real-world-action USP over HTTP. The confirmation is the client's
    explicit POST (the UI shows a confirm step first); the server rebuilds the
    email spec from the insight, re-validates it through guardrails, and only then
    calls the MCP tool. Recipient/SMTP live in the server process's env — never in
    the request, never model-controlled. Bounded by MAX_ACTIONS_PER_SESSION.
    """
    session = _get_session(req.session_id)
    if session.action_count >= config.MAX_ACTIONS_PER_SESSION:
        raise HTTPException(
            status_code=429,
            detail=f"Action limit reached ({config.MAX_ACTIONS_PER_SESSION} emails this session).",
        )

    spec = actions.build_email_alert_spec(req.insight)
    start = time.monotonic()
    try:
        result = actions.execute_action(spec)
    except (ValidationError, actions.ActionError) as exc:
        log_request("email_alert", str(exc), success=False,
                    response_time_seconds=time.monotonic() - start)
        # 502: the request was well-formed but the downstream send failed (e.g.
        # missing SMTP config) — a clean message, never a traceback.
        raise HTTPException(status_code=502, detail=f"Could not send email: {exc}") from exc

    session.action_count += 1
    log_request("email_alert", spec["subject"], success=True,
                response_time_seconds=time.monotonic() - start)
    return {
        "result": result,
        "actions_used": session.action_count,
        "actions_max": config.MAX_ACTIONS_PER_SESSION,
    }


def _sse(event: dict) -> str:
    """Format one dict as a Server-Sent Events `data:` frame."""
    return f"data: {json.dumps(event)}\n\n"


@app.get("/api/insights/stream")
def insights_stream(session_id: str) -> StreamingResponse:
    """Stream the insight pipeline stage-by-stage as Server-Sent Events.

    WHY streaming instead of the plain POST /insights:
        The two-agent pipeline has real, visible phases (summarise -> the
        insight-finder call -> the critic call -> merge). Emitting an event as
        each phase starts/finishes lets the UI show the agents working live —
        the critic's verdicts land one by one — instead of a spinner that hides
        the very architecture that makes this project interesting. Each stage
        reuses the exact same analyst functions the non-streaming path uses.

    Event shapes (all JSON on an SSE `data:` line):
        {"stage": "summarizing"|"generating"|"generated"|"critiquing"|"done", ...}
        {"stage": "insight", "insight": {...}}     one vetted insight
        {"stage": "error", "detail": "..."}        clean, user-facing message
    """
    session = _get_session(session_id)  # 404 before we open the stream

    def gen() -> Iterator[str]:
        if session.request_count >= config.MAX_REQUESTS_PER_SESSION:
            yield _sse({"stage": "error", "detail": (
                f"Session limit reached ({config.MAX_REQUESTS_PER_SESSION} AI requests)."
            )})
            return
        session.request_count += 1
        start = time.monotonic()

        try:
            yield _sse({"stage": "summarizing", "message": "Summarising the cleaned dataset…"})
            summary = session.summary

            yield _sse({"stage": "generating", "message": "Insight-finder is analysing the data…"})
            candidates = generate_insights(summary)
            yield _sse({"stage": "generated", "count": len(candidates),
                        "message": f"Proposed {len(candidates)} candidate insights."})

            yield _sse({"stage": "critiquing", "count": len(candidates),
                        "message": "Critic is independently reviewing each finding…"})
            reviews = review_insights(candidates, summary)
            final = merge_insights_with_reviews(candidates, reviews)

            for ins in final:
                yield _sse({"stage": "insight", "insight": ins})

            avg = (sum(i["confidence"] for i in final) / len(final)) if final else None
            log_request(
                "generate_insights",
                f"{len(final)} of {len(candidates)} candidate insight(s) approved",
                success=True,
                response_time_seconds=time.monotonic() - start,
                confidence_score=avg,
            )
            yield _sse({"stage": "done", "approved": len(final), "candidates": len(candidates),
                        "requests_used": session.request_count})
        except (InsightGenerationError, CriticReviewError, ClaudeConfigError) as exc:
            log_request("generate_insights", str(exc), success=False,
                        response_time_seconds=time.monotonic() - start)
            yield _sse({"stage": "error", "detail": str(exc)})
        except Exception as exc:  # never leak a raw traceback to the stream
            yield _sse({"stage": "error", "detail": f"Unexpected error: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
