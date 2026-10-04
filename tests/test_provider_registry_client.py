from __future__ import annotations

from typing import Any

from underpayment_checker.ingestion import provider_registry_client


def _result(npi: str, taxonomy: str, city: str = "DALLAS", org: str = "Fixture PT LLC") -> dict:
    return {
        "number": int(npi),
        "basic": {"organization_name": org},
        "addresses": [
            {"address_purpose": "MAILING", "city": "PLANO", "state": "TX", "postal_code": "75001"},
            {
                "address_purpose": "LOCATION",
                "city": city,
                "state": "TX",
                "postal_code": "752011234",
            },
        ],
        "taxonomies": [{"desc": taxonomy, "primary": True}, {"desc": "Other", "primary": False}],
    }


def test_filters_on_primary_taxonomy_and_location_city() -> None:
    page = {
        "results": [
            _result("1999999991", "Physical Therapist"),
            _result("1999999992", "Occupational Therapist"),
            _result("1999999993", "Physical Therapist", city="HOUSTON"),
        ]
    }
    providers = list(
        provider_registry_client.iter_providers("Dallas", "TX", fetch=lambda url: page)
    )
    assert [p.npi for p in providers] == ["1999999991"]
    assert providers[0].postal_code == "75201"
    assert providers[0].name == "Fixture PT LLC"


def test_paginates_until_a_short_page() -> None:
    urls: list[str] = []
    full_page = {"results": [_result("1999999991", "Physical Therapist")] * 200}

    def fetch(url: str) -> dict[str, Any]:
        urls.append(url)
        return full_page if len(urls) == 1 else {"results": []}

    list(provider_registry_client.iter_providers("Dallas", "TX", fetch=fetch))
    assert len(urls) == 2
    assert "skip=200" in urls[1]


def test_individual_provider_name() -> None:
    result = _result("1999999991", "Physical Therapist")
    result["basic"] = {"first_name": "ANA", "last_name": "LOPEZ"}
    provider = next(
        provider_registry_client.iter_providers(
            "Dallas", "TX", fetch=lambda url: {"results": [result]}
        )
    )
    assert provider.name == "ANA LOPEZ"


def test_lookup_npi_returns_provider_or_none() -> None:
    found = provider_registry_client.lookup_npi(
        "1999999991", fetch=lambda url: {"results": [_result("1999999991", "Physical Therapist")]}
    )
    assert (
        found is not None and found.npi == "1999999991" and "number=1999999991" in found.source_url
    )
    assert provider_registry_client.lookup_npi("1", fetch=lambda url: {"results": []}) is None
