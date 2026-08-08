"""Unit tests for the cleaning module (production requirement #13).

These test the transformations the resume claims: messy dates, text-format
numbers, duplicates, encoding fallback, and anomaly flagging — all without any
network or Streamlit dependency.
"""

from __future__ import annotations

import pandas as pd

from analyst.cleaning import clean_csv_bytes, clean_dataframe, read_csv_bytes


def _clean(df):
    cleaned, report = clean_dataframe(df)
    return cleaned, report


def test_duplicate_rows_removed_and_reported():
    df = pd.DataFrame({"A": [1, 1, 2], "B": ["x", "x", "y"]})
    cleaned, report = _clean(df)
    assert len(cleaned) == 2
    assert report.duplicate_rows_removed == 1


def test_text_dates_parsed_to_datetime():
    df = pd.DataFrame({"Order Date": ["11/8/2016", "6/12/2017", "not-a-date"]})
    cleaned, report = _clean(df)
    assert pd.api.types.is_datetime64_any_dtype(cleaned["Order Date"])
    assert "Order Date" in report.date_columns_parsed
    assert report.unparseable_dates["Order Date"] == 1  # flagged, not crashed


def test_currency_text_coerced_to_numeric():
    # 4 of 5 values parse (80%) — exactly at the coercion threshold.
    df = pd.DataFrame({"Sales": ["$1,200.50", "300", "€45", "12.5", "oops"]})
    cleaned, report = _clean(df)
    assert pd.api.types.is_numeric_dtype(cleaned["Sales"])
    assert cleaned["Sales"].iloc[0] == 1200.50
    assert "Sales" in report.numeric_columns_coerced
    assert report.failed_numeric_coercions["Sales"] == 1


def test_free_text_column_not_mangled_into_numeric():
    # Only 1 of 4 values parses (<80%) so the column must stay as text.
    df = pd.DataFrame({"Product Name": ["Desk", "Chair", "42", "Lamp"]})
    cleaned, report = _clean(df)
    assert cleaned["Product Name"].dtype == object
    assert "Product Name" not in report.numeric_columns_coerced


def test_categorical_case_whitespace_normalized():
    df = pd.DataFrame({"Region": ["west", "West ", "WEST"]})
    cleaned, _ = _clean(df)
    assert set(cleaned["Region"]) == {"West"}


def test_missing_values_flagged_not_imputed_for_stat_columns():
    df = pd.DataFrame({"Profit": [1.0, None, 3.0], "Postal Code": [None, "123", "456"]})
    cleaned, report = _clean(df)
    # Stat column: flagged, still NaN.
    assert report.missing_values_flagged["Profit"] == 1
    assert cleaned["Profit"].isna().sum() == 1
    # ID-like column: safely filled with sentinel.
    assert report.missing_values_filled["Postal Code"] == 1
    assert (cleaned["Postal Code"] == "UNKNOWN").sum() == 1


def test_ship_before_order_anomaly_flagged():
    df = pd.DataFrame(
        {"Order Date": ["2024-05-10", "2024-05-10"], "Ship Date": ["2024-05-01", "2024-05-12"]}
    )
    _, report = _clean(df)
    assert any("Ship Date precedes Order Date" in a for a in report.anomalies)


def test_negative_sales_and_bad_discount_flagged():
    df = pd.DataFrame({"Sales": [-10.0, 50.0], "Discount": [1.5, 0.2]})
    _, report = _clean(df)
    assert any("negative Sales" in a for a in report.anomalies)
    assert any("Discount outside" in a for a in report.anomalies)


def test_latin1_encoding_fallback():
    raw = "Name,Sales\nCafé señor,100\n".encode("latin-1")
    df, encoding = read_csv_bytes(raw)
    assert encoding == "latin-1"
    assert len(df) == 1


def test_clean_csv_bytes_end_to_end():
    raw = b"Order Date,Sales\n1/5/2024,$100\n1/5/2024,$100\n"
    df, report = clean_csv_bytes(raw)
    assert len(df) == 1  # duplicate dropped
    assert report.original_rows == 2
    assert report.final_rows == 1
