"""Validate the payment totals of a customer and load them into bronze parquet.

The file must contain totals only: one row for each provider, payer, code and year.
The file must not contain patient data, claim numbers or service dates.
HIPAA Safe Harbor de-identification (45 CFR 164.514(b)(2)) removes all date elements
except the year, and all unique identifying numbers. Thus claim-level rows can be
protected health information. The loader rejects such columns before it stores the file.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from underpayment_checker.exceptions import UploadError

REQUIRED_COLUMNS = (
    "provider_npi",
    "payer_id",
    "cpt",
    "year",
    "line_count",
    "total_allowed",
)
OPTIONAL_COLUMNS = (
    "provider_tin",
    "modifier",
    "place_of_service",
    "min_allowed",
    "max_allowed",
)
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
NUMERIC_COLUMNS = ("line_count", "total_allowed", "min_allowed", "max_allowed")

# Parts of column names that show patient-level or claim-level data.
FORBIDDEN_FRAGMENTS = (
    "name",
    "dob",
    "birth",
    "patient",
    "member",
    "subscriber",
    "ssn",
    "mrn",
    "claim",
    "account",
    "address",
    "zip",
    "phone",
    "email",
    "dos",
    "service_date",
    "date",
)

PATTERNS = {
    "provider_npi": (r"\d{10}", "provider_npi must be 10 digits"),
    "year": (r"(19|20)\d{2}", "year must be a 4-digit year only (no months or days)"),
    "cpt": (r"[0-9A-Z]\d{3}[0-9A-Z]", "cpt must be a 5-character CPT/HCPCS code"),
    "provider_tin": (r"(\d{9})?", "provider_tin must be 9 digits or blank"),
    "place_of_service": (r"(\d{2})?", "place_of_service must be a 2-digit code or blank"),
    "modifier": (
        r"([0-9A-Z]{2}(,[0-9A-Z]{2})*)?",
        "modifier must be 2-character codes, comma-separated",
    ),
}


def _normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    return frame


def validate(frame: pd.DataFrame, known_payers: set[str]) -> pd.DataFrame:
    """Return a clean copy of ``frame``. If problems exist, raise :class:`UploadError`."""
    frame = _normalise_columns(frame)
    columns = list(frame.columns)

    suspicious = [c for c in columns if any(fragment in c for fragment in FORBIDDEN_FRAGMENTS)]
    if suspicious:
        raise UploadError(
            f"File rejected: columns {suspicious} look like patient or claim data. "
            f"Send totals only, with columns: {', '.join(ALL_COLUMNS)}"
        )
    if missing := [c for c in REQUIRED_COLUMNS if c not in columns]:
        raise UploadError(f"File rejected: missing columns {missing}")
    if extra := [c for c in columns if c not in ALL_COLUMNS]:
        raise UploadError(
            f"File rejected: unexpected columns {extra}. Allowed: {list(ALL_COLUMNS)}"
        )
    if frame.empty:
        raise UploadError("File rejected: it has no rows")

    frame = frame.reindex(columns=list(ALL_COLUMNS)).fillna("").astype(str)
    frame = frame.apply(lambda column: column.str.strip())
    frame["payer_id"] = frame["payer_id"].str.upper()
    frame["cpt"] = frame["cpt"].str.upper()
    frame["modifier"] = frame["modifier"].str.upper().str.replace(" ", "", regex=False)
    frame["provider_tin"] = frame["provider_tin"].str.replace("-", "", regex=False)

    problems = [
        message
        for column, (pattern, message) in PATTERNS.items()
        if not frame[column].str.fullmatch(pattern).all()
    ]
    if unknown := sorted(set(frame["payer_id"]) - known_payers):
        problems.append(f"unknown payer_id {unknown}; expected one of {sorted(known_payers)}")
    for column in NUMERIC_COLUMNS:
        values = pd.to_numeric(frame[column].replace("", pd.NA), errors="coerce")
        required = column in REQUIRED_COLUMNS
        if (values.isna() & ((frame[column] != "") | required)).any() or (values < 0).any():
            problems.append(f"{column} must be a non-negative number")
    if not frame["line_count"].str.fullmatch(r"[1-9]\d*").all():
        problems.append("line_count must be a whole number of at least 1")
    if problems:
        raise UploadError("File rejected: " + "; ".join(problems))
    return frame


def load_to_bronze(csv_path: Path, known_payers: set[str], out_path: Path) -> int:
    """Validate ``csv_path``. Write it to ``out_path`` with audit columns. Return the row count."""
    raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    frame = validate(raw, known_payers)
    frame["record_source"] = re.sub(r"[^\w.\-]", "_", csv_path.name)
    frame["load_date"] = date.today().isoformat()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out_path, index=False)
    return len(frame)
