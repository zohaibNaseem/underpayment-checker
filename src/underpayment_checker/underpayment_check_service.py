"""End-to-end check. The input is customer payment totals.

The outputs are findings, a PDF report and appeal letters."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from underpayment_checker.ingestion import customer_payment_totals_loader
from underpayment_checker.reference_lists import load_payers
from underpayment_checker.report.appeal_letter_writer import LetterContext, write_letter
from underpayment_checker.report.findings import Findings, load_findings
from underpayment_checker.report.pdf_report_builder import build_report
from underpayment_checker.settings import Settings
from underpayment_checker.transform import sql_pipeline_runner

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckResult:
    findings: Findings
    report_path: Path
    letter_paths: list[Path] = field(default_factory=list)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "customer"


def run_check(
    payments_csv: Path,
    settings: Settings,
    *,
    customer_name: str,
    data_label: str,
    bronze_rates: Path | None = None,
    use_ai_letters: bool = False,
    provider_labels: dict[str, str] | None = None,
) -> CheckResult:
    """Validate ``payments_csv``, compare it with the published rates and write the outputs.

    ``provider_labels`` maps an NPI to a label. The labels replace the NPIs in the report and
    the letters. Use them to hide real providers when the payments are illustrative.
    """
    payers = load_payers(settings.reference_dir)
    payer_names = {payer_id: payer.payer_name for payer_id, payer in payers.items()}
    bronze_payments = settings.bronze_payments_path
    customer_payment_totals_loader.load_to_bronze(payments_csv, set(payers), bronze_payments)

    con = sql_pipeline_runner.run(
        bronze_rates or settings.bronze_rates_path,
        bronze_payments,
        settings,
        output_dir=settings.output_dir,
    )
    findings = load_findings(con)
    if provider_labels:
        findings = findings.with_provider_labels(provider_labels)
    out_dir = settings.reports_dir / _slug(customer_name)
    report_path = build_report(
        findings,
        out_dir / "underpayment_report.pdf",
        customer_name=customer_name,
        data_label=data_label,
        payer_names=payer_names,
    )

    letter_paths = []
    for payer_id in findings.summary.loc[findings.summary["rows_underpaid"] > 0, "payer_id"]:
        context = LetterContext(
            payer_name=payer_names.get(payer_id, payer_id),
            provider_label=customer_name,
            findings=findings.for_payer(payer_id),
        )
        path = out_dir / f"appeal_letter_{_slug(payer_id)}.txt"
        path.write_text(write_letter(context, use_ai=use_ai_letters), encoding="utf-8")
        letter_paths.append(path)

    logger.info(
        "%s: %d rows checked, %d underpaid, gap $%.2f",
        customer_name,
        findings.rows_checked,
        len(findings.underpaid),
        findings.total_gap_usd,
    )
    return CheckResult(findings=findings, report_path=report_path, letter_paths=letter_paths)
