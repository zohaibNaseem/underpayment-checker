"""Reference lists in CSV files: target billing codes, target providers and known payers."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

CODES_FILE = "target_codes.csv"
PROVIDERS_FILE = "target_providers.csv"
PAYERS_FILE = "payers.csv"


@dataclass(frozen=True)
class Provider:
    """A provider that we check rates for. The NPI and the name come from the NPPES registry."""

    npi: str
    name: str
    city: str
    state: str
    postal_code: str
    taxonomy: str
    source_url: str = ""


@dataclass(frozen=True)
class Payer:
    payer_id: str
    payer_name: str
    toc_url: str = ""


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def load_codes(reference_dir: Path) -> set[str]:
    """Return the CPT and HCPCS codes to extract from rate files."""
    return {row["code"] for row in _read_rows(reference_dir / CODES_FILE) if row.get("code")}


def load_providers(reference_dir: Path, filename: str = PROVIDERS_FILE) -> list[Provider]:
    return [Provider(**row) for row in _read_rows(reference_dir / filename)]


def load_payers(reference_dir: Path) -> dict[str, Payer]:
    return {row["payer_id"]: Payer(**row) for row in _read_rows(reference_dir / PAYERS_FILE)}


def write_providers(providers: Iterable[Provider], path: Path) -> int:
    """Write the providers to a CSV file. Return the number of providers."""
    rows = [asdict(provider) for provider in providers]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[f.name for f in fields(Provider)])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
