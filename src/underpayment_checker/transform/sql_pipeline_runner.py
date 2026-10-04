"""Run the silver and gold SQL files in sequence on the bronze parquet files."""

from __future__ import annotations

import logging
from importlib.resources import files
from pathlib import Path

import duckdb
import pandas as pd

from underpayment_checker.settings import Settings

logger = logging.getLogger(__name__)

SQL_FILES = (
    "silver_published_rates.sql",
    "silver_customer_payments.sql",
    "gold_payment_gaps.sql",
    "gold_payer_summary.sql",
)
OUTPUT_TABLES = {
    "silver": ("silver_published_rates", "silver_customer_payments"),
    "gold": ("gold_payment_gaps", "gold_payer_summary"),
}


def _sql(name: str) -> str:
    return files("underpayment_checker.transform").joinpath("sql", name).read_text(encoding="utf-8")


def _quote(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def load_published_rates(bronze_rates: Path) -> pd.DataFrame:
    """Return the silver published-rates table for ``bronze_rates``. The sample report uses it."""
    con = duckdb.connect()
    con.execute(
        "CREATE VIEW bronze_published_rates AS "
        f"SELECT * FROM read_parquet('{_quote(bronze_rates)}')"
    )
    con.execute(_sql("silver_published_rates.sql"))
    return con.execute("SELECT * FROM silver_published_rates").df()


def run(
    bronze_rates: Path,
    bronze_payments: Path,
    settings: Settings,
    *,
    output_dir: Path | None = None,
) -> duckdb.DuckDBPyConnection:
    """Make the silver and gold tables in an in-memory DuckDB. Return the open connection.

    If ``output_dir`` is given, the function also writes each table to
    ``output_dir/<layer>/<table>.parquet``.
    """
    con = duckdb.connect()
    con.execute(
        "CREATE VIEW bronze_published_rates AS "
        f"SELECT * FROM read_parquet('{_quote(bronze_rates)}')"
    )
    con.execute(
        "CREATE VIEW bronze_customer_payment_totals AS "
        f"SELECT * FROM read_parquet('{_quote(bronze_payments)}')"
    )
    con.execute("SET VARIABLE gap_pct_threshold = ?", [settings.gap_pct_threshold])
    con.execute("SET VARIABLE gap_usd_threshold = ?", [settings.gap_usd_threshold])

    for name in SQL_FILES:
        con.execute(_sql(name))
        logger.debug("ran %s", name)

    if output_dir is not None:
        for layer, tables in OUTPUT_TABLES.items():
            layer_dir = output_dir / layer
            layer_dir.mkdir(parents=True, exist_ok=True)
            for table in tables:
                target = _quote(layer_dir / f"{table}.parquet")
                con.execute(f"COPY {table} TO '{target}' (FORMAT parquet)")
    return con
