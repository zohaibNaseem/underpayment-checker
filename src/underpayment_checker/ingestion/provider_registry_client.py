"""Find providers in the public NPPES NPI Registry (npiregistry.cms.hhs.gov).

Use this module to find real physical-therapy providers in a city. Then search for their NPIs
in the rate file of a payer. The taxonomy filter of the API is not exact. Thus the module
filters the results again on the primary taxonomy of each provider.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from underpayment_checker.reference_lists import Provider

logger = logging.getLogger(__name__)

API_URL = "https://npiregistry.cms.hhs.gov/api/"
PAGE_SIZE = 200  # Maximum results for each API request.

Fetcher = Callable[[str], dict[str, Any]]


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def _location(result: dict[str, Any]) -> dict[str, Any]:
    addresses = result.get("addresses") or []
    return next((a for a in addresses if a.get("address_purpose") == "LOCATION"), {})


def _primary_taxonomy(result: dict[str, Any]) -> str:
    taxonomies = result.get("taxonomies") or []
    primary = next((t for t in taxonomies if t.get("primary")), {})
    return str(primary.get("desc") or "").strip()


def _name(result: dict[str, Any]) -> str:
    basic = result.get("basic") or {}
    if basic.get("organization_name"):
        return str(basic["organization_name"])
    return " ".join(p for p in (basic.get("first_name"), basic.get("last_name")) if p)


def _to_provider(result: dict[str, Any], url: str) -> Provider:
    location = _location(result)
    return Provider(
        npi=str(result["number"]),
        name=_name(result),
        city=str(location.get("city", "")),
        state=str(location.get("state", "")),
        postal_code=str(location.get("postal_code", ""))[:5],
        taxonomy=_primary_taxonomy(result),
        source_url=url,
    )


def lookup_npi(npi: str, *, fetch: Fetcher = _fetch_json) -> Provider | None:
    """Return the registry record for one NPI. Return None if the registry does not have the NPI."""
    url = f"{API_URL}?{urllib.parse.urlencode({'version': '2.1', 'number': npi})}"
    results = fetch(url).get("results") or []
    return _to_provider(results[0], url) if results else None


def iter_providers(
    city: str,
    state: str,
    taxonomy: str = "Physical Therapist",
    *,
    max_records: int = 1_200,
    fetch: Fetcher = _fetch_json,
) -> Iterator[Provider]:
    """Yield the providers in ``city`` and ``state`` whose primary taxonomy is ``taxonomy``."""
    for skip in range(0, max_records, PAGE_SIZE):
        query = urllib.parse.urlencode(
            {
                "version": "2.1",
                "taxonomy_description": taxonomy,
                "city": city.upper(),
                "state": state.upper(),
                "limit": PAGE_SIZE,
                "skip": skip,
            }
        )
        url = f"{API_URL}?{query}"
        results = fetch(url).get("results") or []
        for result in results:
            provider = _to_provider(result, url)
            if (
                provider.taxonomy.lower() == taxonomy.lower()
                and provider.city.upper() == city.upper()
            ):
                yield provider
        if len(results) < PAGE_SIZE:
            break
