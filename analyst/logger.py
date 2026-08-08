"""Request logging — production-hardening requirement #12.

WHY CSV instead of SQLite:
    Volume here is single-session, human-scale (bounded by
    config.MAX_REQUESTS_PER_SESSION per session) — a CSV is the simplest thing
    that can be appended to, opened by eye, or loaded straight into pandas for
    the accuracy/validity analysis this log exists to support. There's no
    concurrent-writer contention to justify SQLite's extra moving parts at this
    scale; if this ever became a multi-process server handling many concurrent
    sessions, that would be the trigger to revisit this choice.

WHY logging failures never raise:
    Logging is an observability side-effect, not the actual user-facing
    operation. A disk-full or permissions error while writing the log must never
    take down the insight/critic/Q&A call that already succeeded — so this
    module swallows its own errors (printing to stderr) rather than letting a
    logging bug masquerade as a pipeline bug.
"""

from __future__ import annotations

import csv
import datetime
import os
import sys

from . import config

FIELDNAMES = [
    "timestamp",
    "action",
    "detail",
    "success",
    "response_time_seconds",
    "confidence_score",
]


def log_request(
    action: str,
    detail: str,
    success: bool,
    response_time_seconds: float,
    confidence_score: float | None = None,
) -> None:
    """Append one row to the request log. Never raises."""
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        is_new_file = not os.path.exists(config.LOG_CSV_PATH)
        with open(config.LOG_CSV_PATH, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            if is_new_file:
                writer.writeheader()
            writer.writerow(
                {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "action": action,
                    "detail": detail,
                    "success": success,
                    "response_time_seconds": round(response_time_seconds, 3),
                    "confidence_score": "" if confidence_score is None else round(confidence_score, 3),
                }
            )
    except OSError as exc:  # pragma: no cover - defensive; disk/permission failures
        print(f"[logger] failed to write request log: {exc}", file=sys.stderr)
