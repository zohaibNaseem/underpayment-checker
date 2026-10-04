"""Project paths and business thresholds in one object that you cannot change."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """Settings for one run.

    Attributes:
        root: The project root. The ``data/`` and ``reference/`` folders are in it.
        gap_pct_threshold: The pipeline flags a line only if the gap is more than this share
            of the expected amount.
        gap_usd_threshold: The gap must also be more than this number of dollars.
    """

    root: Path = PROJECT_ROOT
    gap_pct_threshold: float = 0.02
    gap_usd_threshold: float = 50.0

    @classmethod
    def from_env(cls) -> Settings:
        """Make the settings. UPC_ROOT, UPC_GAP_PCT and UPC_GAP_USD replace the defaults."""
        return cls(
            root=Path(os.environ.get("UPC_ROOT", PROJECT_ROOT)),
            gap_pct_threshold=float(os.environ.get("UPC_GAP_PCT", cls.gap_pct_threshold)),
            gap_usd_threshold=float(os.environ.get("UPC_GAP_USD", cls.gap_usd_threshold)),
        )

    @property
    def reference_dir(self) -> Path:
        return self.root / "reference"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def output_dir(self) -> Path:
        """The folder for the silver and gold parquet files. Each layer has its own subfolder."""
        return self.data_dir

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def bronze_rates_path(self) -> Path:
        return self.bronze_dir / "published_rates.parquet"

    @property
    def bronze_payments_path(self) -> Path:
        return self.bronze_dir / "customer_payment_totals.parquet"
