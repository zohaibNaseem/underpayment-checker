from __future__ import annotations

from helpers import INDEX_FIXTURE
from underpayment_checker.ingestion import payer_index_reader


def test_deduplicates_files_ignoring_signed_query_strings() -> None:
    files = payer_index_reader.list_in_network_files(INDEX_FIXTURE)
    assert [f.filename for f in files] == [
        "ppo_in-network-rates.json.gz",
        "hmo_in-network-rates.json.gz",
    ]


def test_counts_plans_across_reporting_structures() -> None:
    ppo, hmo = payer_index_reader.list_in_network_files(INDEX_FIXTURE)
    assert (ppo.plan_count, hmo.plan_count) == (3, 2)


def test_keeps_first_signed_url_for_download() -> None:
    ppo = payer_index_reader.list_in_network_files(INDEX_FIXTURE)[0]
    assert ppo.url.endswith("?sig=abc")


def test_find_files_matches_description_case_insensitively() -> None:
    files = payer_index_reader.list_in_network_files(INDEX_FIXTURE)
    assert [f.description for f in payer_index_reader.find_files(files, "fixture ppo")] == [
        "Fixture PPO in-network file"
    ]
