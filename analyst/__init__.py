"""Autonomous Data Analyst Agent — core package.

Modules:
    config          Central limits/constants (no heavy imports).
    cleaning        Data cleaning + DataQualityReport.
    insight_agent   Insight-finder Claude call (call #1).
    critic_agent    Critic Claude call (call #2).
    pipeline        Orchestration + logging.
    qa_agent        NL follow-up Q&A with session memory.
    charts          Chart-spec rendering (pandas + matplotlib, code-only).
    guardrails      Input validation + destructive-op blocking.
    llm_json        Shared schema-constrained Claude call helper.
    logger          Structured request log (feeds the metrics panel).
"""

__version__ = "0.1.0"
