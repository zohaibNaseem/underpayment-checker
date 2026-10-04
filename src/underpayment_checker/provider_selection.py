"""Select providers that have rates in the rate file of a payer.

There are two methods:

* ``rank_providers_by_code_coverage``: Start from a registry list, for example Dallas physical
  therapists. Keep the providers with the most priced codes in the rate file.
* ``select_from_rate_file``: Start from the rate file. Find each provider in the registry.
  Keep the providers with the correct specialty and state. Use this method when the registry
  list and the rate file have no providers in common, for example in small networks.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb

from underpayment_checker.reference_lists import Provider

Lookup = Callable[[str], Provider | None]

_COVERAGE_SQL = """
    SELECT npi, count(DISTINCT billing_code) AS codes
    FROM read_parquet(?)
    WHERE negotiated_rate > 0
      AND lower(negotiation_arrangement) = 'ffs'
      AND lower(billing_class) IN ('professional', 'both')
      AND lower(negotiated_type) IN ('negotiated', 'fee schedule', 'derived')
    GROUP BY npi
    ORDER BY codes DESC, npi
"""


def _ranked_npis(bronze_rates: Path) -> list[str]:
    """Return the NPIs that have professional dollar rates. The NPI with the most codes is first."""
    rows = duckdb.connect().execute(_COVERAGE_SQL, [bronze_rates.as_posix()]).fetchall()
    return [npi for npi, _ in rows]


def rank_providers_by_code_coverage(
    bronze_rates: Path, candidates: list[Provider], *, top: int = 5
) -> list[Provider]:
    """Return a maximum of ``top`` candidates. The candidates with more priced codes come first."""
    by_npi = {provider.npi: provider for provider in candidates}
    return [by_npi[npi] for npi in _ranked_npis(bronze_rates) if npi in by_npi][:top]


def select_from_rate_file(
    bronze_rates: Path,
    lookup: Lookup,
    *,
    taxonomy_prefix: str,
    state: str,
    top: int = 5,
    max_lookups: int = 300,
) -> list[Provider]:
    """Examine the providers in the file in order of code coverage. Keep the registry matches.

    A provider matches if its primary taxonomy starts with ``taxonomy_prefix`` and its
    location is in ``state``. Thus "Physical Therapist" also matches
    "Physical Therapist, Orthopedic". The function makes a maximum of ``max_lookups`` calls.
    """
    chosen: list[Provider] = []
    for npi in _ranked_npis(bronze_rates)[:max_lookups]:
        provider = lookup(npi)
        if (
            provider is not None
            and provider.taxonomy.lower().startswith(taxonomy_prefix.lower())
            and provider.state.upper() == state.upper()
        ):
            chosen.append(provider)
            if len(chosen) == top:
                break
    return chosen
