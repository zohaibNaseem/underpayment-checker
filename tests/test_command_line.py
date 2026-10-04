from __future__ import annotations

from pathlib import Path

import pytest

from helpers import INDEX_FIXTURE, RATES_FIXTURE, fake_remote_fetch
from underpayment_checker import command_line
from underpayment_checker.ingestion import rate_file_streamer
from underpayment_checker.reference_lists import Provider
from underpayment_checker.settings import Settings


@pytest.fixture
def cli_settings(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("UPC_ROOT", str(settings.root))
    return settings


def test_list_rate_files(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        command_line.main(["list-rate-files", "--index", str(INDEX_FIXTURE), "--keyword", "ppo"])
        == 0
    )
    out = capsys.readouterr().out
    assert "Fixture PPO in-network file" in out and "HMO" not in out


def test_ingest_then_sample_report(
    cli_settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original = rate_file_streamer.ingest_to_bronze

    def ingest_with_fake_remote(*args, **kwargs):
        return original(*args, fetch_remote=fake_remote_fetch, **kwargs)

    monkeypatch.setattr(rate_file_streamer, "ingest_to_bronze", ingest_with_fake_remote)
    assert (
        command_line.main(
            ["ingest-rates", "--source", str(RATES_FIXTURE), "--payer", "BCBSTX", "--all-providers"]
        )
        == 0
    )
    assert command_line.main(["sample-report", "--seed", "3"]) == 0

    out = capsys.readouterr().out
    assert "Rows underpaid:" in out and "Report:" in out
    assert Path(out.split("Report: ")[1].splitlines()[0]).exists()


def test_ingest_requires_codes(cli_settings: Settings) -> None:
    (cli_settings.reference_dir / "target_codes.csv").write_text("code,dispositions,source\n")
    assert (
        command_line.main(["ingest-rates", "--source", str(RATES_FIXTURE), "--payer", "BCBSTX"])
        == 1
    )


def test_unknown_command_exits() -> None:
    with pytest.raises(SystemExit):
        command_line.main(["nope"])


def test_masked_labels_hide_npis() -> None:
    providers = [
        Provider("1999999991", "Real Name", "AUSTIN", "TX", "78701", "Physical Therapist"),
        Provider("1999999992", "Other Name", "LEANDER", "TX", "78641", "Physical Therapist"),
    ]
    assert command_line.masked_labels(providers) == {
        "1999999991": "Provider A (Austin, TX)",
        "1999999992": "Provider B (Leander, TX)",
    }
