"""Manual smoke test for the insight-finder agent — not a pytest test.

Runs the real pipeline (clean -> summarize -> call Claude) against
data/superstore.csv and prints the raw insights so you can eyeball output
quality before the critic agent is built on top of it in Phase 3.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/check_insights.py [path/to/csv]

This intentionally makes a real, billed API call — it is a manual review
tool, not part of the automated (mocked) pytest suite added in Phase 7.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python scripts/check_insights.py` from the repo root without
# installing the package — insert the repo root (this script's parent directory)
# onto sys.path so `analyst` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyst.claude_client import ClaudeConfigError
from analyst.cleaning import clean_csv_bytes
from analyst.insight_agent import InsightGenerationError, build_data_summary, generate_insights


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/superstore.csv"

    with open(path, "rb") as fh:
        raw = fh.read()
    df, report = clean_csv_bytes(raw)
    print(f"Loaded and cleaned {path}: {df.shape[0]} rows x {df.shape[1]} columns.\n")

    summary = build_data_summary(df)
    print("--- Data summary sent to Claude ---")
    print(summary)
    print("--- End summary ---\n")

    try:
        insights = generate_insights(summary)
    except (InsightGenerationError, ClaudeConfigError) as exc:
        print(f"Insight generation failed: {exc}")
        return 1

    print(f"Received {len(insights)} insight(s):\n")
    for i, item in enumerate(insights, start=1):
        print(f"{i}. [{item.get('category')}] {item.get('insight')}")
        print(f"   Supporting data: {item.get('supporting_data')}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
