"""Make the one-page PDF report: total gap, summary by payer, largest gaps and method notes."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from underpayment_checker.report.findings import Findings

TOP_ROWS = 12
INK = colors.HexColor("#1F2937")
ACCENT = colors.HexColor("#B45309")
RULE = colors.HexColor("#D1D5DB")
HEADER_FILL = colors.HexColor("#F3F4F6")

DISCLAIMER = (
    "Findings are lines worth reviewing, not proof of underpayment. Expected amounts use the "
    "lowest rate the payer publishes for the provider under the Transparency in Coverage rule; "
    "the provider's contract governs. Allowed amounts include the patient's share, so "
    "deductibles and co-pays are not counted as gaps. HIGH confidence: one exact published "
    "dollar rate. REVIEW: several rates or a derived (estimated) rate."
)


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], textColor=INK, fontSize=18, alignment=0, spaceAfter=4
        ),
        "meta": ParagraphStyle("meta", parent=base["Normal"], textColor=colors.grey, fontSize=8.5),
        "headline": ParagraphStyle(
            "headline",
            parent=base["Normal"],
            textColor=ACCENT,
            fontSize=15,
            leading=19,
            spaceBefore=8,
            spaceAfter=2,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], textColor=INK, fontSize=11, spaceBefore=10, spaceAfter=4
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], textColor=INK, fontSize=8.5, leading=11
        ),
    }


def _table(rows: list[list[str]], widths: list[float]) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
                ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def build_report(
    findings: Findings,
    output_path: Path,
    *,
    customer_name: str,
    data_label: str,
    payer_names: dict[str, str] | None = None,
) -> Path:
    """Write the PDF to ``output_path``. Return the path."""
    payer_names = payer_names or {}
    styles = _styles()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=f"Underpayment check - {customer_name}",
    )

    story: list = [
        Paragraph(f"Underpayment check: {customer_name}", styles["title"]),
        Paragraph(f"Prepared {date.today():%d %B %Y} | Data: {data_label}", styles["meta"]),
    ]
    underpaid_rows = len(findings.underpaid)
    story.append(
        Paragraph(
            f"{_money(findings.total_gap_usd)} may be recoverable "
            f"across {underpaid_rows} of {findings.rows_checked} rows checked",
            styles["headline"],
        )
    )
    story.append(
        Paragraph(
            f"{_money(findings.high_confidence_gap_usd)} of it is HIGH confidence "
            "(a single exact published dollar rate).",
            styles["body"],
        )
    )

    story.append(Paragraph("By payer", styles["h2"]))
    payer_rows = [
        ["Payer", "Rows checked", "Rows underpaid", "Lines underpaid", "Gap", "High conf."]
    ]
    payer_rows += [
        [
            payer_names.get(row.payer_id, row.payer_id),
            f"{int(row.rows_checked):,}",
            f"{int(row.rows_underpaid):,}",
            f"{int(row.lines_underpaid):,}",
            _money(row.total_gap_usd),
            _money(row.high_confidence_gap_usd),
        ]
        for row in findings.summary.itertuples(index=False)
    ]
    story.append(
        _table(payer_rows, [2.3 * inch, 0.9 * inch, 1.0 * inch, 1.0 * inch, 0.9 * inch, 0.9 * inch])
    )

    story.append(Paragraph(f"Largest gaps (top {TOP_ROWS})", styles["h2"]))
    if findings.underpaid.empty:
        story.append(Paragraph("No rows exceeded the review thresholds.", styles["body"]))
    else:
        gap_rows = [
            ["Provider", "Code", "Lines", "Published rate", "Avg allowed", "Gap", "Confidence"]
        ]
        for row in findings.underpaid.head(TOP_ROWS).itertuples(index=False):
            gap_rows.append(
                [
                    row.provider,
                    row.cpt,
                    f"{row.line_count:,}",
                    _money(row.expected_rate),
                    _money(row.total_allowed / row.line_count),
                    _money(row.gap_usd),
                    row.confidence,
                ]
            )
        story.append(
            _table(
                gap_rows,
                [
                    1.9 * inch,
                    0.6 * inch,
                    0.6 * inch,
                    1.0 * inch,
                    0.9 * inch,
                    0.9 * inch,
                    0.9 * inch,
                ],
            )
        )

    sources = sorted(
        {
            name
            for cell in findings.underpaid.get("source_files", [])
            for name in str(cell).split(",")
        }
        - {""}
    )
    story.append(Paragraph("Evidence and method", styles["h2"]))
    if sources:
        story.append(
            Paragraph("Published-rate source files: " + "; ".join(sources), styles["body"])
        )
        story.append(Spacer(1, 4))
    story.append(Paragraph(DISCLAIMER, styles["body"]))

    doc.build(story)
    return output_path
