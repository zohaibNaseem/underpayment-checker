from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from helpers import payment_row, write_payments
from underpayment_checker.exceptions import UploadError
from underpayment_checker.ingestion import customer_payment_totals_loader as loader

PAYERS = {"BCBSTX"}


def _frame(**overrides: str) -> pd.DataFrame:
    return pd.DataFrame([payment_row(**overrides)])


def test_valid_row_passes_and_is_normalised() -> None:
    cleaned = loader.validate(_frame(payer_id="bcbstx", modifier="gp"), PAYERS)
    assert cleaned.loc[0, "payer_id"] == "BCBSTX"
    assert cleaned.loc[0, "modifier"] == "GP"


def test_tin_dash_is_removed() -> None:
    assert loader.validate(_frame(provider_tin="99-0000001"), PAYERS).loc[0, "provider_tin"] == (
        "990000001"
    )


def test_optional_columns_may_be_absent() -> None:
    frame = _frame()[list(loader.REQUIRED_COLUMNS)]
    cleaned = loader.validate(frame, PAYERS)
    assert list(cleaned.columns) == list(loader.ALL_COLUMNS)


@pytest.mark.parametrize(
    "column", ["patient_name", "member_id", "claim_id", "date_of_service", "dob", "zip_code"]
)
def test_rejects_patient_or_claim_level_columns(column: str) -> None:
    frame = _frame().assign(**{column: "x"})
    with pytest.raises(UploadError, match="patient or claim data"):
        loader.validate(frame, PAYERS)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("year", "2026-03", "4-digit year"),
        ("provider_npi", "12345", "10 digits"),
        ("provider_tin", "12-345", "9 digits"),
        ("place_of_service", "1", "2-digit"),
        ("cpt", "97", "5-character"),
        ("line_count", "abc", "line_count must be"),
        ("line_count", "1.5", "whole number"),  # would crash the SQL integer cast
        ("line_count", "0", "whole number"),
        ("total_allowed", "-5", "total_allowed must be"),
        ("payer_id", "AETNA", "unknown payer_id"),
    ],
)
def test_rejects_bad_values(field: str, value: str, message: str) -> None:
    with pytest.raises(UploadError, match=message):
        loader.validate(_frame(**{field: value}), PAYERS)


def test_rejects_missing_and_unexpected_columns() -> None:
    with pytest.raises(UploadError, match="missing columns"):
        loader.validate(_frame().drop(columns=["year"]), PAYERS)
    with pytest.raises(UploadError, match="unexpected columns"):
        loader.validate(_frame().assign(notes="x"), PAYERS)


def test_rejects_empty_file() -> None:
    with pytest.raises(UploadError, match="no rows"):
        loader.validate(pd.DataFrame(columns=loader.REQUIRED_COLUMNS), PAYERS)


def test_load_to_bronze_adds_audit_columns(tmp_path: Path) -> None:
    csv_path = write_payments(tmp_path / "my file.csv", [payment_row()])
    out = tmp_path / "bronze.parquet"
    assert loader.load_to_bronze(csv_path, PAYERS, out) == 1
    stored = pd.read_parquet(out)
    assert stored.loc[0, "record_source"] == "my_file.csv"
    assert "load_date" in stored.columns
