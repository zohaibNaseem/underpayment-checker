from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from underpayment_checker.ingestion.customer_payment_totals_loader import validate
from underpayment_checker.sample_data import payment_generator as generator
from underpayment_checker.transform.sql_pipeline_runner import load_published_rates


@pytest.fixture
def published(bronze_rates: Path) -> pd.DataFrame:
    return load_published_rates(bronze_rates)


def test_expected_rate_follows_pipeline_matching_rules(published: pd.DataFrame) -> None:
    dataset = generator.generate(published, underpaid_share=0.0)
    key = dataset.answer_key.set_index(["provider_npi", "cpt"])["published_rate"]
    assert key[("1999999991", "97110")] == 40.0  # unmodified rate used for a GP line
    assert key[("1999999992", "97110")] == 38.5  # expired $30 ignored
    assert key[("1999999992", "97112")] == 45.0  # GP-specific rate wins over unmodified $42


def test_plants_exact_share_with_at_least_one(published: pd.DataFrame) -> None:
    rows = len(generator.generate(published).answer_key)
    for share, expected in [(0.0, 1), (0.5, round(0.5 * rows)), (1.0, rows)]:
        planted = generator.generate(published, underpaid_share=share).answer_key
        assert planted["planted_underpayment"].sum() == expected


def test_is_deterministic_for_a_seed(published: pd.DataFrame) -> None:
    first = generator.generate(published, seed=11).payments
    second = generator.generate(published, seed=11).payments
    pd.testing.assert_frame_equal(first, second)


def test_output_passes_customer_validation(published: pd.DataFrame) -> None:
    payments = generator.generate(published).payments.astype(str)
    validate(payments, {"BCBSTX"})
    assert set(payments["modifier"]) == {generator.THERAPY_MODIFIER}


def test_write_creates_both_files(published: pd.DataFrame, tmp_path: Path) -> None:
    payments_path, answers_path = generator.write(generator.generate(published), tmp_path)
    assert payments_path.exists() and answers_path.exists()
