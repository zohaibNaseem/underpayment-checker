"""Write one appeal letter for each payer from the gold findings.

A letter contains only aggregated findings: codes, published rates, line counts and gaps.
The module never sends the uploaded customer file to a different system. If the optional
``anthropic`` package and credentials are available, Claude writes the draft. If not, the
module uses a fixed template.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_LINES_IN_LETTER = 25

SYSTEM_PROMPT = (
    "You draft payment-dispute letters for US medical billing teams. Write a concise, "
    "factual, professional letter from the provider to the payer requesting review and "
    "reprocessing of the listed underpaid services. Use only the facts provided; do not "
    "invent claim numbers, patient details, contract terms or laws. Refer to the rates as "
    "the rates the payer publishes under the Transparency in Coverage rule. Keep "
    "placeholders in square brackets for anything not provided. Output plain text only."
)


@dataclass(frozen=True)
class LetterContext:
    """The facts for the letter to one payer."""

    payer_name: str
    provider_label: str
    findings: pd.DataFrame  # The underpaid rows for this payer.

    @property
    def total_gap_usd(self) -> float:
        return float(self.findings["gap_usd"].sum())

    def fact_lines(self) -> list[str]:
        lines = []
        for row in self.findings.head(MAX_LINES_IN_LETTER).itertuples(index=False):
            average = row.total_allowed / row.line_count
            lines.append(
                f"- {row.provider}, code {row.cpt}, {row.year}: {row.line_count} lines "
                f"allowed at an average of ${average:,.2f} against a published rate of "
                f"${row.expected_rate:,.2f} "
                f"(difference ${row.gap_usd:,.2f}; confidence {row.confidence})"
            )
        return lines


def template_letter(context: LetterContext) -> str:
    """Return a fixed-template letter. Use it when AI drafting is not available or not wanted."""
    facts = "\n".join(context.fact_lines())
    return (
        f"{date.today():%d %B %Y}\n\n"
        f"{context.payer_name}\nProvider Services / Payment Disputes\n[Payer address]\n\n"
        f"Re: Request for review of underpaid services - {context.provider_label}\n\n"
        "Dear Provider Services team,\n\n"
        "We have compared the amounts allowed on the services below with the rates "
        f"{context.payer_name} publishes for this provider under the Transparency in "
        "Coverage rule. "
        "The allowed amounts are below the published rates:\n\n"
        f"{facts}\n\n"
        f"The total difference is ${context.total_gap_usd:,.2f}. We request that you review these "
        "services, reprocess any claims paid below the applicable rate, and remit the difference. "
        "Claim-level detail is available on request.\n\n"
        "Sincerely,\n\n[Name]\n[Title]\n[Provider or billing company]\n[Contact details]\n"
    )


def ai_letter(context: LetterContext, *, client: object | None = None) -> str | None:
    """Write a draft with Claude. If drafting is not possible, log the reason and return None."""
    try:
        import anthropic
    except ImportError:
        logger.info("anthropic package not installed; using the template letter")
        return None

    prompt = (
        f"Payer: {context.payer_name}\nProvider: {context.provider_label}\n"
        f"Total difference: ${context.total_gap_usd:,.2f}\nUnderpaid services:\n"
        + "\n".join(context.fact_lines())
    )
    try:
        client = client or anthropic.Anthropic()
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": "medium"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIConnectionError as error:
        logger.warning("Claude API unreachable (%s); using the template letter", error)
        return None
    except anthropic.APIStatusError as error:
        logger.warning("Claude API error %s; using the template letter", error.status_code)
        return None
    except (anthropic.AnthropicError, TypeError) as error:  # For example, no credentials are set.
        logger.warning("Claude drafting unavailable (%s); using the template letter", error)
        return None

    if response.stop_reason == "refusal":
        logger.warning("Claude declined the request; using the template letter")
        return None
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text or None


def write_letter(
    context: LetterContext, *, use_ai: bool = False, client: object | None = None
) -> str:
    """Return a letter. If ``use_ai`` is set and Claude writes a draft, return that draft."""
    if use_ai and (drafted := ai_letter(context, client=client)):
        return drafted
    return template_letter(context)
