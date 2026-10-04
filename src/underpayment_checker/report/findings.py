"""Findings from the gold tables, in the shape that the report and the letters use."""

from __future__ import annotations

from dataclasses import dataclass, replace

import duckdb
import pandas as pd


@dataclass(frozen=True)
class Findings:
    """All the data that the outputs use. The class reads the gold tables one time."""

    summary: pd.DataFrame  # One row for each payer.
    underpaid: pd.DataFrame  # One row for each underpaid payment row. The largest gap is first.
    rows_checked: int

    @property
    def total_gap_usd(self) -> float:
        return float(self.underpaid["gap_usd"].sum()) if not self.underpaid.empty else 0.0

    @property
    def high_confidence_gap_usd(self) -> float:
        if self.underpaid.empty:
            return 0.0
        high = self.underpaid[self.underpaid["confidence"] == "HIGH"]
        return float(high["gap_usd"].sum())

    def for_payer(self, payer_id: str) -> pd.DataFrame:
        return self.underpaid[self.underpaid["payer_id"] == payer_id]

    def with_provider_labels(self, labels: dict[str, str]) -> Findings:
        """Return a copy in which the ``provider`` column shows ``labels[npi]``, not the NPI.

        Use this method to hide real providers in sample reports with illustrative payments.
        """
        underpaid = self.underpaid.copy()
        underpaid["provider"] = [
            labels.get(npi, provider)
            for npi, provider in zip(underpaid["npi"], underpaid["provider"], strict=True)
        ]
        return replace(self, underpaid=underpaid)


def load_findings(con: duckdb.DuckDBPyConnection) -> Findings:
    """Read the findings from a connection after the SQL pipeline runs."""
    summary = con.execute("SELECT * FROM gold_payer_summary").df()
    underpaid = con.execute(
        """
        SELECT payer_id, npi, 'NPI ' || npi AS provider, cpt, modifier, year, line_count,
               expected_rate, total_allowed, expected_allowed, gap_usd, gap_pct,
               confidence, negotiated_types, source_files
        FROM gold_payment_gaps
        WHERE status = 'UNDERPAID'
        ORDER BY gap_usd DESC
        """
    ).df()
    rows_checked = int(con.execute("SELECT count(*) FROM gold_payment_gaps").fetchone()[0])
    return Findings(summary=summary, underpaid=underpaid, rows_checked=rows_checked)
