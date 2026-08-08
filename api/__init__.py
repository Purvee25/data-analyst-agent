"""FastAPI backend for the React frontend.

WHY a separate API layer (and not more Streamlit):
    The React single-page app needs plain JSON over HTTP, not server-rendered
    widgets. This package exposes the SAME analyst logic (cleaning, the two-agent
    insight pipeline, the Q&A agent, guardrails, logging) through thin JSON
    endpoints. All the intelligence still lives in `analyst/`; this layer only
    translates HTTP <-> those functions and holds per-session state.
"""
