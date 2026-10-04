from __future__ import annotations

from pathlib import Path

from underpayment_checker import reference_lists
from underpayment_checker.reference_lists import Provider
from underpayment_checker.settings import Settings

PROVIDER = Provider("1999999991", "Fixture PT", "DALLAS", "TX", "75201", "Physical Therapist")


def test_load_codes_and_payers(settings: Settings) -> None:
    assert reference_lists.load_codes(settings.reference_dir) == {
        "97110",
        "97112",
        "97140",
        "97530",
    }
    assert reference_lists.load_payers(settings.reference_dir)["BCBSTX"].payer_name == (
        "Fixture Blue Cross"
    )


def test_missing_files_give_empty_results(tmp_path: Path) -> None:
    assert reference_lists.load_codes(tmp_path) == set()
    assert reference_lists.load_providers(tmp_path) == []


def test_providers_round_trip(tmp_path: Path) -> None:
    path = tmp_path / reference_lists.PROVIDERS_FILE
    assert reference_lists.write_providers([PROVIDER], path) == 1
    assert reference_lists.load_providers(tmp_path) == [PROVIDER]
