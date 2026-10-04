from __future__ import annotations

from pathlib import Path

from underpayment_checker.provider_selection import (
    rank_providers_by_code_coverage,
    select_from_rate_file,
)
from underpayment_checker.reference_lists import Provider


def _provider(npi: str) -> Provider:
    return Provider(npi, f"PT {npi}", "DALLAS", "TX", "75201", "Physical Therapist")


def test_ranks_by_number_of_priced_codes(bronze_rates: Path) -> None:
    candidates = [_provider("1999999992"), _provider("1999999991"), _provider("1000000000")]
    ranked = rank_providers_by_code_coverage(bronze_rates, candidates, top=5)
    # Professional ffs dollar rates: 1999999991 has two codes, 1999999992 two; ties sort by NPI.
    assert [p.npi for p in ranked] == ["1999999991", "1999999992"]


def test_top_limits_results(bronze_rates: Path) -> None:
    candidates = [_provider("1999999991"), _provider("1999999992")]
    assert len(rank_providers_by_code_coverage(bronze_rates, candidates, top=1)) == 1


def test_no_candidates(bronze_rates: Path) -> None:
    assert rank_providers_by_code_coverage(bronze_rates, [], top=5) == []


def test_percentage_and_capitation_codes_do_not_count(bronze_rates: Path) -> None:
    # 1999999991 is priced for 97140 (percentage) and 97530 (capitation) too, but only
    # professional fee-for-service dollar rates count towards coverage.
    ranked = rank_providers_by_code_coverage(bronze_rates, [_provider("1999999991")], top=1)
    assert [p.npi for p in ranked] == ["1999999991"]


def _registry(records: dict[str, Provider]):
    calls: list[str] = []

    def lookup(npi: str) -> Provider | None:
        calls.append(npi)
        return records.get(npi)

    return lookup, calls


def test_select_from_rate_file_filters_specialty_and_state(bronze_rates: Path) -> None:
    lookup, _ = _registry(
        {
            "1999999991": Provider("1999999991", "Doc", "DALLAS", "TX", "75201", "Family Medicine"),
            "1999999992": Provider(
                "1999999992", "PT", "AUSTIN", "TX", "78701", "Physical Therapist, Orthopedic"
            ),
        }
    )
    chosen = select_from_rate_file(
        bronze_rates, lookup, taxonomy_prefix="Physical Therapist", state="tx"
    )
    assert [p.npi for p in chosen] == ["1999999992"]


def test_select_from_rate_file_stops_at_top_and_max_lookups(bronze_rates: Path) -> None:
    pt = "Physical Therapist"
    lookup, calls = _registry(
        {
            npi: Provider(npi, "PT", "AUSTIN", "TX", "78701", pt)
            for npi in ("1999999991", "1999999992")
        }
    )
    assert (
        len(select_from_rate_file(bronze_rates, lookup, taxonomy_prefix=pt, state="TX", top=1)) == 1
    )
    assert calls == ["1999999991"]
    calls.clear()
    assert (
        select_from_rate_file(bronze_rates, lookup, taxonomy_prefix=pt, state="TX", max_lookups=0)
        == []
    )
    assert calls == []
