"""Dashboard for the underpayment check.

Upload payment totals. Examine the gaps. Download the report and the letters.

To start the dashboard, run:  streamlit run src/underpayment_checker/app/dashboard.py
The dashboard processes files on this computer. It keeps files only in ``data/``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from underpayment_checker.exceptions import UploadError
from underpayment_checker.ingestion.customer_payment_totals_loader import ALL_COLUMNS
from underpayment_checker.settings import Settings
from underpayment_checker.underpayment_check_service import run_check


def main() -> None:
    st.set_page_config(page_title="Underpayment Checker", layout="wide")
    st.title("Underpayment Checker")
    st.caption("Compares allowed amounts with the rates the payer publishes for each provider.")

    settings = Settings.from_env()
    if not settings.bronze_rates_path.exists():
        st.error("No published rates loaded yet. Run `upc ingest-rates` first.")
        return

    customer = st.text_input("Customer name", "Example Billing Co. (fictional)")
    label = st.text_input("Data label", "illustrative payments; real published rates")
    st.write("Upload a CSV with totals only. Columns:", ", ".join(ALL_COLUMNS))
    upload = st.file_uploader("Payment totals CSV", type="csv")
    if upload is None:
        return

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "upload.csv"
        csv_path.write_bytes(upload.getvalue())
        try:
            result = run_check(csv_path, settings, customer_name=customer, data_label=label)
        except UploadError as error:
            st.error(str(error))
            return

    findings = result.findings
    left, middle, right = st.columns(3)
    left.metric("Rows checked", f"{findings.rows_checked:,}")
    middle.metric("Possible gap", f"${findings.total_gap_usd:,.2f}")
    right.metric("High confidence", f"${findings.high_confidence_gap_usd:,.2f}")

    st.subheader("By payer")
    st.dataframe(findings.summary, hide_index=True, use_container_width=True)
    st.subheader("Underpaid rows")
    st.dataframe(findings.underpaid, hide_index=True, use_container_width=True)

    st.download_button(
        "Download PDF report", result.report_path.read_bytes(), file_name="underpayment_report.pdf"
    )
    for path in result.letter_paths:
        st.download_button(f"Download {path.name}", path.read_bytes(), file_name=path.name)


if __name__ == "__main__":
    main()
