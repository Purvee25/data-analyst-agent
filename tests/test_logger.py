"""Tests for the request logger (analyst/logger.py).

The logger is observability infrastructure: it must write well-formed rows and,
critically, must NEVER raise — a logging failure must not take down the
user-facing operation that already succeeded.
"""

from __future__ import annotations

import pandas as pd

from analyst import config, logger


def test_writes_header_and_row(monkeypatch, tmp_path):
    path = tmp_path / "requests.csv"
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LOG_CSV_PATH", str(path))

    logger.log_request("generate_insights", "3 approved", success=True, response_time_seconds=1.234, confidence_score=0.777)
    logger.log_request("ask", "q", success=False, response_time_seconds=0.5)

    df = pd.read_csv(path)
    assert list(df.columns) == logger.FIELDNAMES
    assert len(df) == 2
    assert df.iloc[0]["confidence_score"] == 0.777
    # A None confidence is written as an empty cell, not the string "None".
    assert pd.isna(df.iloc[1]["confidence_score"])


def test_never_raises_on_unwritable_path(monkeypatch, tmp_path):
    # Point the log at a path whose parent is a file, so mkdir/open fails —
    # the logger must swallow the OSError, not propagate it.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    monkeypatch.setattr(config, "LOG_DIR", str(blocker / "sub"))
    monkeypatch.setattr(config, "LOG_CSV_PATH", str(blocker / "sub" / "requests.csv"))

    # Must not raise.
    logger.log_request("ask", "q", success=True, response_time_seconds=0.1)
