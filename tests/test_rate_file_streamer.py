from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from helpers import RATES_FIXTURE, TARGET_CODES, TARGET_NPIS, fake_remote_fetch
from underpayment_checker.exceptions import IngestionError
from underpayment_checker.ingestion import rate_file_streamer


def test_keeps_only_target_codes_and_providers(bronze_rates: Path) -> None:
    rows = pd.read_parquet(bronze_rates)
    assert set(rows["billing_code"]) == TARGET_CODES  # 99213 skipped
    assert set(rows["npi"]) == TARGET_NPIS  # 1999999993 skipped


def test_resolves_remote_provider_reference(bronze_rates: Path) -> None:
    rows = pd.read_parquet(bronze_rates)
    remote = rows[rows["npi"] == "1999999992"]
    assert not remote.empty
    assert set(remote["tin_value"]) == {"990000002"}


def test_explodes_place_of_service_and_keeps_modifiers(bronze_rates: Path) -> None:
    rows = pd.read_parquet(bronze_rates)
    fee = rows[
        (rows["npi"] == "1999999991")
        & (rows["billing_code"] == "97110")
        & (rows["billing_class"] == "professional")
    ]
    assert sorted(fee["place_of_service"]) == ["11", "22"]
    assert "GP" in set(rows["modifiers"])


def test_audit_columns(bronze_rates: Path) -> None:
    rows = pd.read_parquet(bronze_rates)
    assert rows["source_file"].eq(RATES_FIXTURE.name).all()
    assert rows["load_date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()


def test_reads_gzip(gzipped_rates: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.parquet"
    count = rate_file_streamer.ingest_to_bronze(
        str(gzipped_rates),
        "BCBSTX",
        TARGET_CODES,
        TARGET_NPIS,
        out,
        fetch_remote=fake_remote_fetch,
    )
    assert count == len(pd.read_parquet(out)) > 0


def test_no_npi_filter_keeps_every_provider(tmp_path: Path) -> None:
    out = tmp_path / "all.parquet"
    rate_file_streamer.ingest_to_bronze(
        str(RATES_FIXTURE), "BCBSTX", TARGET_CODES, None, out, fetch_remote=fake_remote_fetch
    )
    assert "1999999993" in set(pd.read_parquet(out)["npi"])


def test_rejects_rates_before_provider_references(tmp_path: Path) -> None:
    data = json.loads(RATES_FIXTURE.read_text(encoding="utf-8"))
    reordered = {
        "in_network": data["in_network"],
        "provider_references": data["provider_references"],
    }
    source = tmp_path / "reordered.json"
    source.write_text(json.dumps(reordered), encoding="utf-8")
    with pytest.raises(IngestionError, match="single-pass"):
        list(
            rate_file_streamer.iter_rates(
                str(source), "BCBSTX", TARGET_CODES, TARGET_NPIS, fetch_remote=fake_remote_fetch
            )
        )


def test_empty_result_still_writes_valid_parquet(tmp_path: Path) -> None:
    out = tmp_path / "empty.parquet"
    count = rate_file_streamer.ingest_to_bronze(
        str(RATES_FIXTURE), "BCBSTX", {"00000"}, TARGET_NPIS, out, fetch_remote=fake_remote_fetch
    )
    assert count == 0
    assert list(pd.read_parquet(out).columns) == list(rate_file_streamer.SCHEMA.names)
