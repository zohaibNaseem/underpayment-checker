"""Read the Transparency in Coverage index file of a payer.

The index is a table of contents. It lists each in-network rate file and the plans that each
file covers. BCBS Texas publishes one index each month, for example
``2026-08-20_Blue-Cross-and-Blue-Shield-of-Texas_index.json``.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RateFile:
    """One in-network rate file in an index."""

    description: str
    url: str
    plan_count: int

    @property
    def filename(self) -> str:
        return self.url.split("?", 1)[0].rsplit("/", 1)[-1]


def list_in_network_files(index_path: Path) -> list[RateFile]:
    """Return each in-network file one time. The file that covers the most plans is first.

    The ``url`` keeps signed query strings because some hosts need them.
    The function ignores query strings when it removes duplicates.
    """
    index = json.loads(index_path.read_text(encoding="utf-8"))
    plan_counts: Counter[str] = Counter()
    first_seen: dict[str, tuple[str, str]] = {}

    for structure in index.get("reporting_structure", []):
        plans = len(structure.get("reporting_plans", []))
        for entry in structure.get("in_network_files", []):
            key = entry["location"].split("?", 1)[0]
            plan_counts[key] += plans
            first_seen.setdefault(key, (entry.get("description", ""), entry["location"]))

    return [
        RateFile(description=first_seen[key][0], url=first_seen[key][1], plan_count=count)
        for key, count in plan_counts.most_common()
    ]


def find_files(files: list[RateFile], keyword: str) -> list[RateFile]:
    """Keep the files whose description or file name contains ``keyword``. Case is not important."""
    needle = keyword.lower()
    return [f for f in files if needle in f.description.lower() or needle in f.filename.lower()]
