"""Stream Transparency in Coverage (TiC) in-network rate files into bronze parquet.

A rate file can be many gigabytes. Thus this module never loads a full file into memory.
It reads the file one time, as a stream of JSON events:

* In BCBS Texas files, ``provider_references`` comes before ``in_network``. The module makes a
  small map from each provider-group ID to its providers. The map keeps only the target NPIs.
* The module builds an ``in_network`` item only when its billing code is a target code.
  It skips all other items, event by event, and does not build them.

The field names agree with the CMS schema:
https://github.com/CMSgov/price-transparency-guide/tree/master/schemas/in-network-rates
"""

from __future__ import annotations

import gzip
import json
import logging
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, BinaryIO

import ijson
import pyarrow as pa
import pyarrow.parquet as pq

from underpayment_checker.exceptions import IngestionError

logger = logging.getLogger(__name__)

PROVIDER_REF_ITEM = "provider_references.item"
IN_NETWORK_ITEM = "in_network.item"
BATCH_ROWS = 50_000

ProviderKey = tuple[str, str, str]  # (npi, tin_type, tin_value)
RemoteFetcher = Callable[[str], dict[str, Any]]


@dataclass(slots=True)
class RateRecord:
    """One published price for one provider, billing code and place of service."""

    payer_id: str
    billing_code_type: str
    billing_code: str
    negotiation_arrangement: str
    npi: str
    tin_type: str
    tin_value: str
    negotiated_type: str
    negotiated_rate: float | None
    billing_class: str
    place_of_service: str
    modifiers: str
    expiration_date: str
    source_file: str
    load_date: str


SCHEMA = pa.schema(
    [
        (name, pa.float64() if name == "negotiated_rate" else pa.string())
        for name in RateRecord.__dataclass_fields__
    ]
)


@contextmanager
def open_stream(source: str) -> Iterator[BinaryIO]:
    """Open a local path or an http(s) URL. Decompress ``.gz`` sources automatically."""
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
        raw: BinaryIO = urllib.request.urlopen(request, timeout=300)
    else:
        raw = open(source, "rb")  # noqa: SIM115 - the finally block closes the file
    try:
        path_part = source.split("?", 1)[0]
        yield gzip.GzipFile(fileobj=raw) if path_part.endswith(".gz") else raw
    finally:
        raw.close()


def fetch_remote_reference(url: str) -> dict[str, Any]:
    """Get a provider-reference file from the ``location`` that a rate file gives."""
    with open_stream(url) as stream:
        return json.load(stream)


def _providers(groups: Iterable[dict[str, Any]] | None, npis: set[str] | None) -> list[ProviderKey]:
    found: list[ProviderKey] = []
    for group in groups or []:
        tin = group.get("tin") or {}
        for npi in group.get("npi") or []:
            npi_str = str(npi)
            if npis is None or npi_str in npis:
                found.append((npi_str, str(tin.get("type") or ""), str(tin.get("value") or "")))
    return found


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float | Decimal) else None


def _records(
    item: dict[str, Any],
    references: dict[Any, list[ProviderKey]],
    npis: set[str] | None,
    payer_id: str,
    source_file: str,
    today: str,
) -> Iterator[RateRecord]:
    """Change one in_network item into flat rate records."""
    for rate in item.get("negotiated_rates") or []:
        providers = [
            p for ref in rate.get("provider_references") or [] for p in references.get(ref, [])
        ]
        providers += _providers(
            rate.get("provider_groups"), npis
        )  # Older schemas put provider groups in the rate.
        if not providers:
            continue
        for price in rate.get("negotiated_prices") or []:
            places = [str(code) for code in price.get("service_code") or []] or [""]
            modifiers = ",".join(str(m) for m in price.get("billing_code_modifier") or [])
            for npi, tin_type, tin_value in providers:
                for place in places:
                    yield RateRecord(
                        payer_id=payer_id,
                        billing_code_type=str(item.get("billing_code_type") or ""),
                        billing_code=str(item.get("billing_code") or ""),
                        negotiation_arrangement=str(item.get("negotiation_arrangement") or ""),
                        npi=npi,
                        tin_type=tin_type,
                        tin_value=tin_value,
                        negotiated_type=str(price.get("negotiated_type") or ""),
                        negotiated_rate=_as_float(price.get("negotiated_rate")),
                        billing_class=str(price.get("billing_class") or ""),
                        place_of_service=place,
                        modifiers=modifiers,
                        expiration_date=str(price.get("expiration_date") or ""),
                        source_file=source_file,
                        load_date=today,
                    )


def iter_rates(
    source: str,
    payer_id: str,
    codes: set[str],
    npis: set[str] | None = None,
    *,
    fetch_remote: RemoteFetcher = fetch_remote_reference,
) -> Iterator[RateRecord]:
    """Yield rate records for the target ``codes`` in one pass. Keep only ``npis`` if given.

    Raises:
        IngestionError: if an in_network item that uses provider references comes before
            ``provider_references``. One pass is then not possible for this file.
    """
    source_file = source.split("?", 1)[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    today = date.today().isoformat()
    references: dict[Any, list[ProviderKey]] = {}
    references_done = False
    builder: ijson.ObjectBuilder | None = None
    building = ""  # The item prefix that the builder collects.
    skipping = False
    seen_items = 0

    with open_stream(source) as stream:
        for prefix, event, value in ijson.parse(stream, use_float=False):
            if skipping:
                if prefix == IN_NETWORK_ITEM and event == "end_map":
                    skipping = False
                continue

            if prefix in (PROVIDER_REF_ITEM, IN_NETWORK_ITEM) and event == "start_map":
                builder, building = ijson.ObjectBuilder(), prefix
            if builder is None:
                if prefix == "provider_references" and event == "end_array":
                    references_done = True
                continue

            is_code = building == IN_NETWORK_ITEM and prefix == f"{IN_NETWORK_ITEM}.billing_code"
            if is_code and str(value) not in codes:
                builder, skipping = None, True
                continue

            builder.event(event, value)
            if prefix != building or event != "end_map":
                continue

            obj, builder = builder.value, None
            if building == PROVIDER_REF_ITEM:
                groups = obj.get("provider_groups")
                if groups is None and obj.get("location"):
                    groups = fetch_remote(obj["location"]).get("provider_groups")
                if found := _providers(groups, npis):
                    references[obj["provider_group_id"]] = found
                continue

            seen_items += 1
            if not references_done and any(
                r.get("provider_references") for r in obj.get("negotiated_rates") or []
            ):
                raise IngestionError(
                    f"{source_file}: in_network item before provider_references; "
                    "single-pass parsing is not possible for this file"
                )
            yield from _records(obj, references, npis, payer_id, source_file, today)

    logger.info(
        "%s: %d target provider groups, %d target billing-code items",
        source_file,
        len(references),
        seen_items,
    )


def ingest_to_bronze(
    source: str,
    payer_id: str,
    codes: set[str],
    npis: set[str] | None,
    out_path: Path,
    *,
    fetch_remote: RemoteFetcher = fetch_remote_reference,
) -> int:
    """Stream the matching rates into ``out_path`` in batches. Return the row count."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    batch: list[dict[str, Any]] = []
    with pq.ParquetWriter(out_path, SCHEMA) as writer:
        for record in iter_rates(source, payer_id, codes, npis, fetch_remote=fetch_remote):
            batch.append(asdict(record))
            if len(batch) >= BATCH_ROWS:
                writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
                total += len(batch)
                batch.clear()
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
            total += len(batch)
    logger.info("bronze rates: %d rows -> %s", total, out_path)
    return total
