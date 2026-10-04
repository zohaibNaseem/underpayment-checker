"""Matching rules of the silver/gold SQL, checked row by row against the fixture rates."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import payment_row, write_payments
from underpayment_checker.ingestion import customer_payment_totals_loader
from underpayment_checker.settings import Settings
from underpayment_checker.transform import sql_pipeline_runner


def _gap_row(settings: Settings, bronze_rates: Path, **overrides: str) -> dict:
    csv_path = write_payments(settings.root / "payments.csv", [payment_row(**overrides)])
    customer_payment_totals_loader.load_to_bronze(
        csv_path, {"BCBSTX"}, settings.bronze_payments_path
    )
    con = sql_pipeline_runner.run(bronze_rates, settings.bronze_payments_path, settings)
    frame = con.execute("SELECT * FROM gold_payment_gaps").df()
    assert len(frame) == 1
    return frame.iloc[0].to_dict()


def test_silver_keeps_only_professional_ffs_dollar_rates(bronze_rates: Path) -> None:
    rates = sql_pipeline_runner.load_published_rates(bronze_rates)
    assert set(rates["negotiated_type"]) <= {"negotiated", "fee schedule", "derived"}
    assert "97140" not in set(rates["cpt"])  # percentage of charges is not a dollar rate
    assert "97530" not in set(rates["cpt"])  # capitation excluded
    assert 55.0 not in set(rates["rate"])  # institutional price excluded


@pytest.mark.parametrize(
    ("overrides", "expected_rate", "confidence"),
    [
        ({}, 40.0, "HIGH"),  # GP modifier falls back to the unmodified rate
        ({"provider_npi": "1999999992"}, 38.5, "HIGH"),  # expired $30 rate ignored
        ({"cpt": "97112"}, 44.1, "REVIEW"),  # derived rate is an estimate
        ({"provider_npi": "1999999992", "cpt": "97112"}, 45.0, "HIGH"),  # exact GP rate wins
        ({"provider_npi": "1999999992", "cpt": "97112", "modifier": ""}, 42.0, "HIGH"),
        ({"place_of_service": "22"}, 40.0, "HIGH"),
        ({"provider_tin": "990000001"}, 40.0, "HIGH"),  # file has "99-0000001"
        ({"provider_tin": "99-0000001"}, 40.0, "HIGH"),
    ],
)
def test_expected_rate_matching(
    settings: Settings, bronze_rates: Path, overrides: dict, expected_rate: float, confidence: str
) -> None:
    row = _gap_row(settings, bronze_rates, **overrides)
    assert row["expected_rate"] == pytest.approx(expected_rate)
    assert row["confidence"] == confidence


@pytest.mark.parametrize(
    "overrides",
    [
        {"cpt": "97140"},  # only a percentage rate exists
        {"provider_tin": "123456789"},  # TIN does not match
        {"provider_npi": "1999999992", "place_of_service": "22"},  # no rate at that place
        {"provider_npi": "1999999999"},  # provider not in the file
    ],
)
def test_no_published_rate(settings: Settings, bronze_rates: Path, overrides: dict) -> None:
    row = _gap_row(settings, bronze_rates, **overrides)
    assert row["status"] == "NO_PUBLISHED_RATE"


def test_underpaid_when_above_both_thresholds(settings: Settings, bronze_rates: Path) -> None:
    row = _gap_row(settings, bronze_rates, total_allowed="3500", min_allowed="35")
    assert row["status"] == "UNDERPAID"
    assert row["gap_usd"] == pytest.approx(500.0)
    assert row["gap_pct"] == pytest.approx(0.125)
    assert row["some_lines_below_rate"]


@pytest.mark.parametrize(
    "total_allowed",
    [
        "3970",  # $30 gap: below the $50 threshold
        "4000",  # paid in full
        "4100",  # overpaid
    ],
)
def test_not_flagged_below_thresholds(
    settings: Settings, bronze_rates: Path, total_allowed: str
) -> None:
    assert _gap_row(settings, bronze_rates, total_allowed=total_allowed)["status"] == "OK"


def test_percentage_threshold_applies(settings: Settings, bronze_rates: Path) -> None:
    # $60 gap on $4,000 expected = 1.5%, below the 2% threshold.
    assert _gap_row(settings, bronze_rates, total_allowed="3940")["status"] == "OK"


def test_writes_layer_parquet_files(settings: Settings, bronze_rates: Path) -> None:
    csv_path = write_payments(settings.root / "payments.csv", [payment_row()])
    customer_payment_totals_loader.load_to_bronze(
        csv_path, {"BCBSTX"}, settings.bronze_payments_path
    )
    sql_pipeline_runner.run(
        bronze_rates, settings.bronze_payments_path, settings, output_dir=settings.output_dir
    )
    for layer, tables in sql_pipeline_runner.OUTPUT_TABLES.items():
        for table in tables:
            assert (settings.output_dir / layer / f"{table}.parquet").exists()
