from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from underpayment_checker.report.findings import Findings
from underpayment_checker.report.pdf_report_builder import build_report

pymupdf = pytest.importorskip("pymupdf")


def _findings(underpaid_rows: int) -> Findings:
    underpaid = pd.DataFrame(
        {
            "payer_id": ["BCBSTX"] * underpaid_rows,
            "npi": ["1999999991"] * underpaid_rows,
            "provider": ["NPI 1999999991"] * underpaid_rows,
            "cpt": ["97110"] * underpaid_rows,
            "line_count": [100] * underpaid_rows,
            "expected_rate": [40.0] * underpaid_rows,
            "total_allowed": [3500.0] * underpaid_rows,
            "gap_usd": [500.0] * underpaid_rows,
            "confidence": ["HIGH"] * underpaid_rows,
            "source_files": ["rates.json.gz"] * underpaid_rows,
        }
    )
    summary = pd.DataFrame(
        [
            {
                "payer_id": "BCBSTX",
                "rows_checked": 20,
                "rows_underpaid": underpaid_rows,
                "lines_underpaid": float(100 * underpaid_rows),  # DuckDB sums arrive as floats
                "total_gap_usd": 500.0 * underpaid_rows,
                "high_confidence_gap_usd": 500.0 * underpaid_rows,
            }
        ]
    )
    return Findings(summary=summary, underpaid=underpaid, rows_checked=20)


def _text(path: Path) -> str:
    with pymupdf.open(path) as document:
        return "".join(page.get_text() for page in document)


def test_report_contains_headline_payer_and_disclaimer(tmp_path: Path) -> None:
    path = build_report(
        _findings(3),
        tmp_path / "report.pdf",
        customer_name="Test Co",
        data_label="illustrative",
        payer_names={"BCBSTX": "Fixture Blue Cross"},
    )
    text = _text(path)
    assert "$1,500.00 may be recoverable" in text
    assert "Fixture Blue Cross" in text
    assert "rates.json.gz" in text
    assert "not proof of underpayment" in text
    assert "300.0" not in text  # counts print as whole numbers


def test_report_fits_on_one_page_with_many_rows(tmp_path: Path) -> None:
    path = build_report(
        _findings(40), tmp_path / "report.pdf", customer_name="Test Co", data_label="illustrative"
    )
    with pymupdf.open(path) as document:
        assert document.page_count == 1


def test_report_without_findings(tmp_path: Path) -> None:
    path = build_report(
        _findings(0), tmp_path / "report.pdf", customer_name="Test Co", data_label="illustrative"
    )
    assert "No rows exceeded the review thresholds" in _text(path)
