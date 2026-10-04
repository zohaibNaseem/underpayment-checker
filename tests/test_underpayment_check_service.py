"""End-to-end: illustrative payments must flag every planted gap and nothing else."""

from __future__ import annotations

from pathlib import Path

import pytest

from underpayment_checker.sample_data import payment_generator as generator
from underpayment_checker.settings import Settings
from underpayment_checker.transform.sql_pipeline_runner import load_published_rates
from underpayment_checker.underpayment_check_service import run_check


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_finds_exactly_the_planted_underpayments(
    settings: Settings, bronze_rates: Path, seed: int
) -> None:
    dataset = generator.generate(load_published_rates(bronze_rates), underpaid_share=0.5, seed=seed)
    payments_csv, _ = generator.write(dataset, settings.data_dir / "sample")

    result = run_check(payments_csv, settings, customer_name="Test Co", data_label="illustrative")

    flagged = set(
        zip(result.findings.underpaid["npi"], result.findings.underpaid["cpt"], strict=True)
    )
    key = dataset.answer_key
    planted = key[key["planted_underpayment"]]
    assert flagged == set(zip(planted["provider_npi"], planted["cpt"], strict=True))
    assert result.findings.total_gap_usd == pytest.approx(
        planted["planted_gap_usd"].sum(), abs=0.05
    )
    assert result.findings.summary["total_gap_usd"].sum() == pytest.approx(
        result.findings.total_gap_usd, abs=0.01
    )


def test_writes_report_and_one_letter_per_underpaid_payer(
    settings: Settings, bronze_rates: Path
) -> None:
    dataset = generator.generate(load_published_rates(bronze_rates), underpaid_share=1.0)
    payments_csv, _ = generator.write(dataset, settings.data_dir / "sample")

    result = run_check(payments_csv, settings, customer_name="Test Co", data_label="illustrative")

    assert result.report_path.exists()
    assert [path.name for path in result.letter_paths] == ["appeal_letter_bcbstx.txt"]
    assert "Fixture Blue Cross" in result.letter_paths[0].read_text(encoding="utf-8")


def test_provider_labels_replace_npis_in_outputs(settings: Settings, bronze_rates: Path) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    dataset = generator.generate(load_published_rates(bronze_rates), underpaid_share=1.0)
    payments_csv, _ = generator.write(dataset, settings.data_dir / "sample")
    labels = {"1999999991": "Provider A (Austin, TX)", "1999999992": "Provider B (Austin, TX)"}

    result = run_check(
        payments_csv,
        settings,
        customer_name="Test Co",
        data_label="illustrative",
        provider_labels=labels,
    )

    with pymupdf.open(result.report_path) as document:
        text = "".join(page.get_text() for page in document)
    letter = result.letter_paths[0].read_text(encoding="utf-8")
    for output in (text, letter):
        assert "Provider A (Austin, TX)" in output
        assert "1999999991" not in output and "1999999992" not in output
