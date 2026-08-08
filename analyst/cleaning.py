"""Data cleaning + quality reporting for the Autonomous Data Analyst Agent.

WHY this module is standalone (no Streamlit / no Anthropic imports):
    Cleaning is the foundation every other phase stands on. Keeping it free of UI
    and API dependencies means (a) it is trivially unit-testable without mocking a
    web framework, (b) it can be run from the command line to sanity-check a new
    file, and (c) a bug here never brings down the network layers and vice versa.

WHY we return a structured report alongside the DataFrame:
    A junior analyst who "just cleaned the data" silently is untrustworthy. We make
    every transformation *auditable*: the DataQualityReport records what was changed
    and what was merely flagged, so the UI can show it and the logger can persist it.
    "Fixed" (we changed the data) and "flagged" (we noticed but did NOT change it)
    are kept deliberately separate — imputing values you don't understand is how you
    invent fake insights, so we lean toward flagging over silently mutating.

Design principle: never crash on messy input. Every risky coercion is wrapped so a
bad cell degrades to NaN + a flag, not an exception.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# Columns whose *names* contain any of these tokens are treated as dates and
# parsed to real datetimes. Name-based detection is cheap and predictable; we
# confirm by actually attempting the parse and flagging failures.
_DATE_NAME_TOKENS = ("date",)

# Known categorical columns where inconsistent casing/whitespace ("west" vs
# "West ") is common and meaningful to normalise. Kept as a hint list, not a hard
# requirement — unknown datasets still get generic whitespace trimming.
_CATEGORICAL_HINTS = ("region", "category", "sub-category", "segment", "ship mode")


@dataclass
class DataQualityReport:
    """Structured, serialisable record of everything cleaning did or noticed.

    Kept as a plain dataclass (not a dict) so field names are discoverable and
    typo-proof at call sites, while still converting cleanly to dict/markdown for
    the UI and the request log.
    """

    original_rows: int = 0
    original_cols: int = 0
    final_rows: int = 0
    final_cols: int = 0

    encoding_used: str = "utf-8"

    # Actions we TOOK (data was mutated).
    duplicate_rows_removed: int = 0
    columns_renamed: dict[str, str] = field(default_factory=dict)
    date_columns_parsed: list[str] = field(default_factory=list)
    numeric_columns_coerced: list[str] = field(default_factory=list)
    categorical_columns_normalized: list[str] = field(default_factory=list)
    missing_values_filled: dict[str, int] = field(default_factory=dict)

    # Things we NOTICED but did not silently change (flags for human judgement).
    missing_values_flagged: dict[str, int] = field(default_factory=dict)
    unparseable_dates: dict[str, int] = field(default_factory=dict)
    failed_numeric_coercions: dict[str, int] = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_shape": [self.original_rows, self.original_cols],
            "final_shape": [self.final_rows, self.final_cols],
            "encoding_used": self.encoding_used,
            "duplicate_rows_removed": self.duplicate_rows_removed,
            "columns_renamed": self.columns_renamed,
            "date_columns_parsed": self.date_columns_parsed,
            "numeric_columns_coerced": self.numeric_columns_coerced,
            "categorical_columns_normalized": self.categorical_columns_normalized,
            "missing_values_filled": self.missing_values_filled,
            "missing_values_flagged": self.missing_values_flagged,
            "unparseable_dates": self.unparseable_dates,
            "failed_numeric_coercions": self.failed_numeric_coercions,
            "anomalies": self.anomalies,
        }

    def to_markdown(self) -> str:
        """Human-readable summary for the Streamlit UI / CLI output."""
        lines = ["### Data Quality Report", ""]
        lines.append(
            f"- **Rows:** {self.original_rows:,} → {self.final_rows:,} "
            f"(**Columns:** {self.original_cols} → {self.final_cols})"
        )
        lines.append(f"- **Encoding used to read file:** `{self.encoding_used}`")
        lines.append(f"- **Exact duplicate rows removed:** {self.duplicate_rows_removed}")

        if self.date_columns_parsed:
            lines.append(f"- **Date columns parsed:** {', '.join(self.date_columns_parsed)}")
        if self.numeric_columns_coerced:
            lines.append(
                f"- **Numeric columns coerced from text:** {', '.join(self.numeric_columns_coerced)}"
            )
        if self.categorical_columns_normalized:
            lines.append(
                "- **Categorical columns normalized (case/whitespace):** "
                f"{', '.join(self.categorical_columns_normalized)}"
            )
        if self.missing_values_filled:
            lines.append(f"- **Missing values filled:** {self.missing_values_filled}")

        # Flags — surfaced prominently because these need a human's eye.
        if self.missing_values_flagged:
            lines.append(f"- ⚠️ **Missing values flagged (not filled):** {self.missing_values_flagged}")
        if self.unparseable_dates:
            lines.append(f"- ⚠️ **Unparseable date cells:** {self.unparseable_dates}")
        if self.failed_numeric_coercions:
            lines.append(f"- ⚠️ **Non-numeric cells set to NaN:** {self.failed_numeric_coercions}")
        if self.anomalies:
            lines.append("- ⚠️ **Logical anomalies flagged:**")
            for a in self.anomalies:
                lines.append(f"    - {a}")

        if not any(
            [
                self.duplicate_rows_removed,
                self.missing_values_flagged,
                self.unparseable_dates,
                self.failed_numeric_coercions,
                self.anomalies,
            ]
        ):
            lines.append("")
            lines.append("_No significant data quality issues detected._")
        return "\n".join(lines)


def read_csv_bytes(raw: bytes) -> tuple[pd.DataFrame, str]:
    """Read raw CSV bytes into a DataFrame, tolerating messy encodings.

    WHY encoding fallback: the Superstore file (and most real exports) contain
    non-UTF-8 bytes (e.g. Windows-1252 punctuation in product names). A naive
    ``pd.read_csv`` raises UnicodeDecodeError and the whole app dies. We try
    strict UTF-8 first (the correct case), then fall back to latin-1, which maps
    every byte to a character and therefore never fails — worst case a few
    characters look odd, which is far better than a crash.

    Returns the DataFrame and the encoding that actually worked (recorded in the
    quality report for transparency).
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
            return df, encoding
        except UnicodeDecodeError:
            continue
        except Exception as exc:  # pragma: no cover - surfaced to caller as clean error
            raise ValueError(f"Could not parse CSV: {exc}") from exc
    # If even latin-1 failed, the bytes are not tabular text we can recover.
    raise ValueError("File could not be decoded as UTF-8 or Latin-1 text.")


def _looks_like_date_column(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in _DATE_NAME_TOKENS)


def _is_id_like(name: str) -> bool:
    """Columns that are identifiers, not quantities (postal codes, IDs).

    Used in two places: they are excluded from numeric coercion (a zip code is
    not a number — coercing drops leading zeros and invites nonsense averages),
    and their missing values may be safely filled with a sentinel.
    """
    lowered = name.lower()
    return "postal" in lowered or lowered.endswith("id") or "code" in lowered


def _coerce_numeric_series(series: pd.Series) -> tuple[pd.Series, int]:
    """Coerce a text series to numeric, stripping currency/thousands separators.

    Returns the coerced series and the count of cells that were non-empty but
    could not be parsed (these become NaN and are flagged, never guessed at).
    """
    if pd.api.types.is_numeric_dtype(series):
        return series, 0

    cleaned = (
        series.astype("string")
        .str.replace(r"[,$€£%]", "", regex=True)
        .str.strip()
    )
    coerced = pd.to_numeric(cleaned, errors="coerce")
    # A failure = original had a value but coercion produced NaN.
    failures = int(((coerced.isna()) & (cleaned.notna()) & (cleaned != "")).sum())
    return coerced, failures


def clean_dataframe(df: pd.DataFrame, encoding_used: str = "utf-8") -> tuple[pd.DataFrame, DataQualityReport]:
    """Clean a raw DataFrame and produce a DataQualityReport.

    Steps, in order (each records to the report):
        1. Normalise column names (strip whitespace).
        2. Drop exact duplicate rows.
        3. Parse date-named columns to datetime; flag unparseable cells.
        4. Coerce numeric-looking text columns to numbers; flag failures.
        5. Trim string whitespace; title-case known categorical columns.
        6. Record missing values (fill only where safe, e.g. ID-like codes).
        7. Flag logical anomalies (negative sales, ship < order, bad discounts).

    The input DataFrame is not mutated in place; we operate on a copy so callers
    keep their original if they need it.
    """
    report = DataQualityReport(
        original_rows=len(df),
        original_cols=df.shape[1],
        encoding_used=encoding_used,
    )
    df = df.copy()

    # --- 1. Column name hygiene -------------------------------------------
    renamed = {c: c.strip() for c in df.columns if c != c.strip()}
    if renamed:
        df = df.rename(columns=renamed)
        report.columns_renamed = renamed

    # --- 2. Exact duplicate rows ------------------------------------------
    before = len(df)
    df = df.drop_duplicates()
    report.duplicate_rows_removed = before - len(df)

    # --- 3. Dates ----------------------------------------------------------
    for col in df.columns:
        if not _looks_like_date_column(col):
            continue
        original_non_null = df[col].notna().sum()
        # format inference; dayfirst=False matches the US M/D/Y Superstore format.
        parsed = pd.to_datetime(df[col], errors="coerce", format="mixed")
        unparseable = int((parsed.isna() & df[col].notna()).sum())
        df[col] = parsed
        report.date_columns_parsed.append(col)
        if unparseable:
            report.unparseable_dates[col] = unparseable

    # --- 4. Numeric coercion ----------------------------------------------
    # Only attempt on object/string columns that are NOT dates. A column is
    # accepted as numeric if the majority of its non-null values parse — this
    # avoids mangling free-text columns that happen to contain a stray number.
    for col in df.columns:
        if col in report.date_columns_parsed:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        if _is_id_like(col):
            continue  # identifiers are not quantities; keep them as text
        coerced, failures = _coerce_numeric_series(df[col])
        non_null = df[col].notna().sum()
        parsed_ok = coerced.notna().sum()
        # Heuristic: treat as numeric only if >=80% of non-null values parsed.
        if non_null > 0 and parsed_ok / non_null >= 0.8:
            df[col] = coerced
            report.numeric_columns_coerced.append(col)
            if failures:
                report.failed_numeric_coercions[col] = failures

    # --- 5. String / categorical normalisation ----------------------------
    for col in df.columns:
        if df[col].dtype != object:
            continue
        # Trim surrounding whitespace on every string column.
        df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
        # Title-case known categoricals so "west" and "West " collapse together.
        if col.lower() in _CATEGORICAL_HINTS:
            df[col] = df[col].map(lambda v: v.title() if isinstance(v, str) else v)
            report.categorical_columns_normalized.append(col)

    # --- 6. Missing values -------------------------------------------------
    for col in df.columns:
        missing = int(df[col].isna().sum())
        if missing == 0:
            continue
        # Safe fill: ID/code-like columns can be filled with a sentinel without
        # distorting any statistic (they are never aggregated numerically).
        # Cast to object first — pandas raises if a string sentinel is written
        # into a numeric dtype (e.g. Postal Code that read_csv parsed as int).
        if _is_id_like(col):
            df[col] = df[col].astype(object).fillna("UNKNOWN")
            report.missing_values_filled[col] = missing
        else:
            # Everything else is FLAGGED, not imputed — we refuse to invent
            # values for columns that feed statistics/insights.
            report.missing_values_flagged[col] = missing

    # --- 7. Logical anomaly flags -----------------------------------------
    # Every numeric check is guarded by is_numeric_dtype: a column that failed
    # the 80% coercion threshold stays as text, and comparing text to a number
    # would raise. Guarding keeps the "never crash on messy input" contract.
    cols_lower = {c.lower(): c for c in df.columns}

    def _numeric(name: str) -> pd.Series | None:
        col = cols_lower.get(name)
        if col is not None and pd.api.types.is_numeric_dtype(df[col]):
            return df[col]
        return None

    sales = _numeric("sales")
    if sales is not None:
        neg = int((sales < 0).sum())
        if neg:
            report.anomalies.append(f"{neg} row(s) with negative Sales.")
    quantity = _numeric("quantity")
    if quantity is not None:
        nonpos = int((quantity <= 0).sum())
        if nonpos:
            report.anomalies.append(f"{nonpos} row(s) with non-positive Quantity.")
    discount = _numeric("discount")
    if discount is not None:
        bad = int(((discount < 0) | (discount > 1)).sum())
        if bad:
            report.anomalies.append(f"{bad} row(s) with Discount outside the 0–1 range.")
    if "order date" in cols_lower and "ship date" in cols_lower:
        od, sd = cols_lower["order date"], cols_lower["ship date"]
        both = df[od].notna() & df[sd].notna()
        backwards = int((df.loc[both, sd] < df.loc[both, od]).sum())
        if backwards:
            report.anomalies.append(f"{backwards} row(s) where Ship Date precedes Order Date.")

    report.final_rows = len(df)
    report.final_cols = df.shape[1]
    return df, report


def clean_csv_bytes(raw: bytes) -> tuple[pd.DataFrame, DataQualityReport]:
    """Convenience entry point: raw bytes -> (clean DataFrame, report)."""
    df, encoding = read_csv_bytes(raw)
    return clean_dataframe(df, encoding_used=encoding)


def _cli() -> None:  # pragma: no cover - manual utility
    """Run cleaning against a file path and print the report. Standalone usage:

        python -m analyst.cleaning data/superstore.csv
    """
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "data/superstore.csv"
    with open(path, "rb") as fh:
        raw = fh.read()
    df, report = clean_csv_bytes(raw)
    print(report.to_markdown())
    print("\nDtypes after cleaning:")
    print(df.dtypes)


if __name__ == "__main__":  # pragma: no cover
    _cli()
