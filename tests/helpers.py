"""Test helpers and constants. All NPIs and TINs in tests are fictional."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

FIXTURES = Path(__file__).parent / "fixtures"
RATES_FIXTURE = FIXTURES / "in_network_rates_sample.json"
INDEX_FIXTURE = FIXTURES / "payer_index_sample.json"
TARGET_CODES = {"97110", "97112", "97140", "97530"}
TARGET_NPIS = {"1999999991", "1999999992"}
REMOTE_GROUP_3 = {
    "provider_groups": [{"npi": [1999999992], "tin": {"type": "ein", "value": "990000002"}}]
}


def fake_remote_fetch(url: str) -> dict[str, Any]:
    """Stand-in for fetching a remote provider-reference file."""
    assert url == "remote://group-3"
    return REMOTE_GROUP_3


def payment_row(**overrides: Any) -> dict[str, str]:
    """A valid payment-totals row; override any field."""
    row = {
        "provider_npi": "1999999991",
        "provider_tin": "",
        "payer_id": "BCBSTX",
        "cpt": "97110",
        "modifier": "GP",
        "place_of_service": "",
        "year": "2026",
        "line_count": "100",
        "total_allowed": "4000.00",
        "min_allowed": "40.00",
        "max_allowed": "40.00",
    }
    row.update({key: str(value) for key, value in overrides.items()})
    return row


def write_payments(path: Path, rows: list[dict[str, str]]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path
