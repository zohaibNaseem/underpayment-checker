"""Shared pytest fixtures."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import pytest

from helpers import RATES_FIXTURE, TARGET_CODES, TARGET_NPIS, fake_remote_fetch
from underpayment_checker.ingestion import rate_file_streamer
from underpayment_checker.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings rooted in a temporary project with minimal reference files."""
    reference = tmp_path / "reference"
    reference.mkdir()
    (reference / "payers.csv").write_text(
        "payer_id,payer_name,toc_url\nBCBSTX,Fixture Blue Cross,\n", encoding="utf-8"
    )
    codes = "".join(f"{code},5,fixture\n" for code in sorted(TARGET_CODES))
    (reference / "target_codes.csv").write_text(
        "code,dispositions,source\n" + codes, encoding="utf-8"
    )
    return Settings(root=tmp_path)


@pytest.fixture
def gzipped_rates(tmp_path: Path) -> Path:
    target = tmp_path / "in_network_rates_sample.json.gz"
    with RATES_FIXTURE.open("rb") as src, gzip.open(target, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return target


@pytest.fixture
def bronze_rates(settings: Settings) -> Path:
    """Bronze published rates built from the fixture rate file (target NPIs only)."""
    rate_file_streamer.ingest_to_bronze(
        str(RATES_FIXTURE),
        "BCBSTX",
        TARGET_CODES,
        TARGET_NPIS,
        settings.bronze_rates_path,
        fetch_remote=fake_remote_fetch,
    )
    return settings.bronze_rates_path
