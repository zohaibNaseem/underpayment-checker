"""Make illustrative payment totals on real published rates.

Each provider, payer and code with a published rate gets one payment row. A fixed share of
the rows gets a planted underpayment. All other rows get the exact published rate. The answer
key lets the tests prove that the pipeline finds each planted gap and flags no other row.

Each row has the GP therapy modifier. CMS requires this modifier on "always therapy" codes.
Thus the rows test the fallback to rates without a modifier. Each output of this module
must have the label "illustrative payments; real published rates".
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

THERAPY_MODIFIER = "GP"


@dataclass(frozen=True)
class SampleDataset:
    payments: pd.DataFrame
    answer_key: pd.DataFrame


def _expected_rates(published_rates: pd.DataFrame, year: int) -> pd.DataFrame:
    """Return the rate that the pipeline expects for a GP line, for each payer, NPI and code.

    This function uses the rules of gold_payment_gaps.sql. A rate for the GP modifier has
    priority. If no GP rate exists, the rate without a modifier applies. The function uses
    the lowest rate that is valid in ``year``.
    """
    modifier = published_rates["modifier"].fillna("")
    rates = published_rates[modifier.isin(["", THERAPY_MODIFIER])].copy()
    expiry = pd.to_datetime(rates["expiration_date"], errors="coerce")
    rates = rates[expiry.isna() | (expiry >= pd.Timestamp(year=year, month=1, day=1))]
    rates["exact_modifier"] = rates["modifier"] == THERAPY_MODIFIER
    keys = ["payer_id", "npi", "cpt"]
    preferred = rates[
        rates["exact_modifier"] == rates.groupby(keys)["exact_modifier"].transform("max")
    ]
    return (
        preferred.groupby(keys, as_index=False)["rate"].min().sort_values(keys, ignore_index=True)
    )


def generate(
    published_rates: pd.DataFrame,
    *,
    year: int = 2026,
    underpaid_share: float = 0.25,
    seed: int = 7,
) -> SampleDataset:
    """Make payment totals and an answer key from a silver_published_rates frame."""
    expected = _expected_rates(published_rates, year)
    rng = random.Random(seed)
    count = len(expected)
    planted_size = max(1, round(underpaid_share * count)) if count else 0
    planted = set(rng.sample(range(count), planted_size))

    payments, answers = [], []
    for index, row in enumerate(expected.itertuples(index=False)):
        lines = rng.randint(40, 400)
        per_line = row.rate
        if index in planted:
            per_line = round(row.rate * (1 - rng.uniform(0.10, 0.25)), 2)
        total = round(per_line * lines, 2)
        payments.append(
            {
                "provider_npi": row.npi,
                "provider_tin": "",
                "payer_id": row.payer_id,
                "cpt": row.cpt,
                "modifier": THERAPY_MODIFIER,
                "place_of_service": "",
                "year": year,
                "line_count": lines,
                "total_allowed": total,
                "min_allowed": per_line,
                "max_allowed": per_line,
            }
        )
        answers.append(
            {
                "provider_npi": row.npi,
                "payer_id": row.payer_id,
                "cpt": row.cpt,
                "published_rate": row.rate,
                "planted_underpayment": index in planted,
                "planted_gap_usd": round(row.rate * lines - total, 2),
            }
        )
    return SampleDataset(pd.DataFrame(payments), pd.DataFrame(answers))


def write(dataset: SampleDataset, out_dir: Path) -> tuple[Path, Path]:
    """Write the payments and the answer key to CSV files. Return the two paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payments_path = out_dir / "sample_payment_totals.csv"
    answers_path = out_dir / "sample_answer_key.csv"
    dataset.payments.to_csv(payments_path, index=False)
    dataset.answer_key.to_csv(answers_path, index=False)
    return payments_path, answers_path
