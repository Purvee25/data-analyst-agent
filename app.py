"""Streamlit UI for the Autonomous Data Analyst Agent.

WHY this file contains almost no business logic:
    Every capability lives in the `analyst` package (cleaning, insight/critic
    pipeline, Q&A, guardrails, charts, logging) where it is importable and
    unit-testable without Streamlit. This file only: holds session state,
    enforces the per-session rate limit, calls the package, and renders results.
    That makes the error-handling requirement auditable at a glance — every
    external call below sits inside a try/except that shows a clean message.

Run locally:
    export ANTHROPIC_API_KEY=sk-ant-...
    streamlit run app.py
"""

from __future__ import annotations

import os
import time

import pandas as pd
import streamlit as st

from analyst import actions, config, guardrails
from analyst.charts import render_chart
from analyst.claude_client import ClaudeConfigError
from analyst.cleaning import clean_csv_bytes
from analyst.logger import log_request
from analyst.pipeline import PipelineError, run_insight_pipeline
from analyst.qa_agent import QAError, answer_question, trim_history

# Anchored to this file so `streamlit run` works from any working directory.
DEFAULT_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "superstore.csv")

st.set_page_config(page_title="Autonomous Data Analyst", page_icon="📊", layout="wide")


# --- Session state ----------------------------------------------------------
def _init_state() -> None:
    defaults = {
        "df": None,               # cleaned DataFrame
        "report_md": None,        # data-quality report markdown
        "summary": None,          # LLM-ready data summary (built once per dataset)
        "insights": None,         # final (post-critic) insights
        "chat": [],               # [{"role", "content", "chart_spec"?}] for display
        "qa_history": [],         # trimmed message history resent to Claude
        "requests_used": 0,       # billable requests this session (rate limit)
        "dataset_name": None,
        "actions_used": 0,        # confirmed side-effecting actions this session (rate limit)
        "pending_action_key": None,  # insight index awaiting email confirm, or None
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


_init_state()


def _rate_limit_ok() -> bool:
    return st.session_state.requests_used < config.MAX_REQUESTS_PER_SESSION


def _consume_request() -> None:
    st.session_state.requests_used += 1


def _actions_limit_ok() -> bool:
    return st.session_state.actions_used < config.MAX_ACTIONS_PER_SESSION


def _consume_action() -> None:
    st.session_state.actions_used += 1


# --- Data loading -----------------------------------------------------------
def _load_dataset(raw: bytes, name: str) -> None:
    """Validate, clean, and stash a dataset; reset all derived state."""
    guardrails.validate_upload(raw, name)
    df, report = clean_csv_bytes(raw)
    guardrails.validate_row_count(df)

    st.session_state.df = df
    st.session_state.report_md = report.to_markdown()
    st.session_state.dataset_name = name
    st.session_state.summary = None
    st.session_state.insights = None
    st.session_state.chat = []
    st.session_state.qa_history = []


def _get_summary() -> str:
    """Build the LLM data summary once per dataset and cache it in state."""
    if st.session_state.summary is None:
        from analyst.insight_agent import build_data_summary

        st.session_state.summary = build_data_summary(st.session_state.df)
    return st.session_state.summary


# --- Sidebar: dataset, limits, and the observability panel (USP #3) ---------
with st.sidebar:
    st.title("📊 Data Analyst Agent")

    uploaded = st.file_uploader("Upload a CSV (max 5 MB)", type=["csv"])
    use_demo = st.button("Use demo dataset (Superstore)", use_container_width=True)

    if uploaded is not None and uploaded.name != st.session_state.dataset_name:
        try:
            _load_dataset(uploaded.getvalue(), uploaded.name)
        except (guardrails.ValidationError, ValueError) as exc:
            st.error(str(exc))
    elif use_demo:
        try:
            with open(DEFAULT_DATA_PATH, "rb") as fh:
                _load_dataset(fh.read(), os.path.basename(DEFAULT_DATA_PATH))
        except FileNotFoundError:
            st.error("Demo dataset not found at data/superstore.csv.")
        except (guardrails.ValidationError, ValueError) as exc:
            st.error(str(exc))

    used = st.session_state.requests_used
    st.progress(
        min(used / config.MAX_REQUESTS_PER_SESSION, 1.0),
        text=f"API requests: {used} / {config.MAX_REQUESTS_PER_SESSION} this session",
    )

    # --- Observability panel: the request log as a live accuracy metric -----
    st.divider()
    st.subheader("📈 Agent metrics")
    st.caption("Computed from the structured request log (logs/requests.csv).")
    if os.path.exists(config.LOG_CSV_PATH):
        try:
            log_df = pd.read_csv(config.LOG_CSV_PATH)
            total = len(log_df)
            success_rate = log_df["success"].mean() * 100 if total else 0.0
            avg_latency = log_df["response_time_seconds"].mean() if total else 0.0
            conf = pd.to_numeric(log_df["confidence_score"], errors="coerce").dropna()

            col_a, col_b = st.columns(2)
            col_a.metric("Requests logged", f"{total:,}")
            col_b.metric("Success rate", f"{success_rate:.0f}%")
            col_c, col_d = st.columns(2)
            col_c.metric("Avg latency", f"{avg_latency:.1f}s")
            col_d.metric("Avg confidence", f"{conf.mean():.2f}" if not conf.empty else "—")
            if len(conf) >= 2:
                st.line_chart(conf.reset_index(drop=True), height=120)
        except Exception:  # a malformed log line must never break the UI
            st.caption("Log file exists but could not be parsed.")
    else:
        st.caption("No requests logged yet.")


# --- Main area ---------------------------------------------------------------
if st.session_state.df is None:
    st.header("Autonomous Data Analyst Agent")
    st.markdown(
        """
Upload a CSV (or use the demo Superstore dataset) and this agent will:

1. **Clean the data** with auditable, code-based fixes and a quality report.
2. **Proactively find insights** — no prompting needed (Claude call #1).
3. **Critique its own findings** for statistical validity with an independent
   second model call — weak claims get downgraded or rejected before you see
   them (Claude call #2).
4. **Answer follow-up questions** in plain English with session memory and
   auto-generated charts.

Every request is validated, rate-limited, and logged — see *Agent metrics* in
the sidebar.
"""
    )
    st.stop()

df = st.session_state.df
st.header(f"Dataset: {st.session_state.dataset_name}")
st.caption(f"{df.shape[0]:,} rows × {df.shape[1]} columns after cleaning")

with st.expander("🧹 Data quality report", expanded=False):
    st.markdown(st.session_state.report_md)
with st.expander("👀 Preview (first 20 rows)", expanded=False):
    st.dataframe(df.head(20), use_container_width=True)

# --- Insights ----------------------------------------------------------------
st.subheader("🔍 Proactive insights")

if st.session_state.insights is None:
    if st.button("Generate insights", type="primary", disabled=not _rate_limit_ok()):
        if not _rate_limit_ok():
            st.warning("Session request limit reached — refresh to start a new session.")
        else:
            _consume_request()
            with st.spinner("Analyzing data and critiquing findings (2 Claude calls)…"):
                try:
                    st.session_state.insights = run_insight_pipeline(df)
                    st.rerun()
                except (PipelineError, ClaudeConfigError) as exc:
                    st.error(f"Insight generation failed: {exc}")
    if not _rate_limit_ok():
        st.warning("Session request limit reached — refresh the page to start a new session.")
else:
    insights = st.session_state.insights
    if not insights:
        st.info(
            "The critic rejected every candidate insight — nothing met the "
            "statistical bar. That's the guardrail working, not a bug."
        )
    for idx, item in enumerate(insights):
        confidence = item.get("confidence", 0.0)
        verdict = item.get("critic_verdict", "approve")
        badge = "✅" if verdict == "approve" else "⚠️"
        action_key = f"insight_{idx}"
        with st.container(border=True):
            st.markdown(f"{badge} **[{item.get('category', '?')}]** {item.get('insight', '')}")
            st.progress(confidence, text=f"Confidence: {confidence:.2f} ({verdict})")
            with st.expander("Supporting data & critic reasoning"):
                st.markdown(f"**Supporting data:** {item.get('supporting_data', '—')}")
                st.markdown(f"**Critic says:** {item.get('critic_reasoning', '—')}")

            if st.session_state.pending_action_key == action_key:
                dest = config.ALERT_EMAIL_TO or "(no ALERT_EMAIL_TO configured)"
                st.warning(f"Send this insight as an email alert to **{dest}**?")
                col_confirm, col_cancel = st.columns(2)
                if col_confirm.button("Confirm send", key=f"confirm_{action_key}", type="primary"):
                    spec = actions.build_email_alert_spec(item)
                    start = time.monotonic()
                    try:
                        result = actions.execute_action(spec)
                        _consume_action()
                        log_request("email_alert", spec["subject"], success=True,
                                    response_time_seconds=time.monotonic() - start)
                        st.success(result)
                    except (guardrails.ValidationError, actions.ActionError) as exc:
                        log_request("email_alert", str(exc), success=False,
                                    response_time_seconds=time.monotonic() - start)
                        st.error(f"Could not send email: {exc}")
                    st.session_state.pending_action_key = None
                if col_cancel.button("Cancel", key=f"cancel_{action_key}"):
                    st.session_state.pending_action_key = None
                    st.rerun()
            else:
                if st.button(
                    "📧 Email this insight", key=action_key, disabled=not _actions_limit_ok()
                ):
                    st.session_state.pending_action_key = action_key
                    st.rerun()
                if not _actions_limit_ok():
                    st.caption("Action limit reached for this session.")

# --- Q&A with memory + auto-charts --------------------------------------------
st.subheader("💬 Ask a follow-up question")

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart_spec"):
            try:
                st.pyplot(render_chart(df, msg["chart_spec"]))
            except Exception:
                pass  # a chart that fails to re-render must not break history display

question = st.chat_input("e.g. Which region has the lowest profit margin?")
if question:
    try:
        guardrails.validate_question(question)
    except guardrails.ValidationError as exc:
        st.error(str(exc))
        st.stop()

    if not _rate_limit_ok():
        st.warning("Session request limit reached — refresh the page to start a new session.")
        st.stop()

    st.session_state.chat.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    _consume_request()
    start = time.monotonic()
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                result = answer_question(
                    question, _get_summary(), history=st.session_state.qa_history
                )
            except (QAError, ClaudeConfigError) as exc:
                log_request("qa", str(exc), success=False,
                            response_time_seconds=time.monotonic() - start)
                st.error(f"Could not answer that question: {exc}")
                st.stop()

        st.markdown(result["answer"])

        chart_spec = None
        if result.get("chart"):
            try:
                chart_spec = guardrails.validate_chart_spec(result["chart"], df)
                st.pyplot(render_chart(df, chart_spec))
            except guardrails.ValidationError:
                chart_spec = None  # invalid spec: show the text answer, skip the chart
            except Exception:
                chart_spec = None

    log_request("qa", question[:200], success=True,
                response_time_seconds=time.monotonic() - start)

    # Persist both the display history and the model-facing memory.
    st.session_state.chat.append(
        {"role": "assistant", "content": result["answer"], "chart_spec": chart_spec}
    )
    st.session_state.qa_history = trim_history(
        st.session_state.qa_history
        + [
            {"role": "user", "content": question},
            {"role": "assistant", "content": result["answer"]},
        ]
    )
