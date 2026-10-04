"""Command-line interface. Use ``upc <command>`` or ``python -m underpayment_checker <command>``.

The usual sequence of commands is:

    upc list-rate-files --index data/raw/<index>.json --keyword "Blue Choice PPO"
    upc download --url <rate-file-url> --dest data/raw/<file>.json.gz
    upc find-providers --city Dallas --state TX
    upc ingest-rates --source data/raw/<file>.json.gz --payer BCBSTX
    upc select-providers --top 5
    upc sample-report
    upc check --input <customer_totals.csv> --customer "Customer name"
"""

from __future__ import annotations

import argparse
import logging
import string
from collections.abc import Sequence
from pathlib import Path

from underpayment_checker.ingestion import (
    payer_index_reader,
    provider_registry_client,
    rate_file_streamer,
    resumable_download,
)
from underpayment_checker.provider_selection import (
    rank_providers_by_code_coverage,
    select_from_rate_file,
)
from underpayment_checker.reference_lists import (
    PROVIDERS_FILE,
    Provider,
    load_codes,
    load_providers,
    write_providers,
)
from underpayment_checker.sample_data import payment_generator
from underpayment_checker.settings import Settings
from underpayment_checker.transform.sql_pipeline_runner import load_published_rates
from underpayment_checker.underpayment_check_service import CheckResult, run_check

logger = logging.getLogger("underpayment_checker")

CANDIDATES_FILE = "candidate_providers.csv"
SAMPLE_CUSTOMER = "Example Billing Co. (fictional)"
SAMPLE_LABEL = "illustrative payments; real published rates"


def masked_labels(providers: list[Provider]) -> dict[str, str]:
    """Give each real provider a label, for example "Provider A (Austin, TX)".

    Sample reports use these labels. Thus a sample report does not show a real provider
    with an illustrative underpayment amount."""
    return {
        provider.npi: f"Provider {string.ascii_uppercase[index % 26]}"
        f" ({provider.city.title()}, {provider.state})"
        for index, provider in enumerate(providers)
    }


def _print_result(result: CheckResult) -> None:
    findings = result.findings
    print(f"Rows checked: {findings.rows_checked}")
    print(f"Rows underpaid: {len(findings.underpaid)}")
    print(
        f"Total gap: ${findings.total_gap_usd:,.2f} "
        f"(high confidence ${findings.high_confidence_gap_usd:,.2f})"
    )
    print(f"Report: {result.report_path}")
    for path in result.letter_paths:
        print(f"Letter: {path}")


def cmd_list_rate_files(args: argparse.Namespace, _settings: Settings) -> int:
    files = payer_index_reader.list_in_network_files(Path(args.index))
    if args.keyword:
        files = payer_index_reader.find_files(files, args.keyword)
    for rate_file in files[: args.limit]:
        print(f"{rate_file.plan_count:>8} plans | {rate_file.description} | {rate_file.url}")
    return 0


def cmd_download(args: argparse.Namespace, _settings: Settings) -> int:
    resumable_download.download(args.url, Path(args.dest))
    return 0


def cmd_find_providers(args: argparse.Namespace, settings: Settings) -> int:
    providers = list(provider_registry_client.iter_providers(args.city, args.state, args.taxonomy))
    count = write_providers(providers, settings.reference_dir / CANDIDATES_FILE)
    print(f"{count} {args.taxonomy} providers in {args.city}, {args.state} -> {CANDIDATES_FILE}")
    return 0


def cmd_ingest_rates(args: argparse.Namespace, settings: Settings) -> int:
    codes = load_codes(settings.reference_dir)
    if not codes:
        print("reference/target_codes.csv is empty")
        return 1
    npis: set[str] | None = None
    if not args.all_providers:
        providers = load_providers(settings.reference_dir, CANDIDATES_FILE) + load_providers(
            settings.reference_dir
        )
        npis = {provider.npi for provider in providers} or None
    rows = rate_file_streamer.ingest_to_bronze(
        args.source, args.payer, codes, npis, settings.bronze_rates_path
    )
    print(f"{rows} published-rate rows -> {settings.bronze_rates_path}")
    return 0


def cmd_select_providers(args: argparse.Namespace, settings: Settings) -> int:
    if args.from_rate_file:
        chosen = select_from_rate_file(
            settings.bronze_rates_path,
            provider_registry_client.lookup_npi,
            taxonomy_prefix=args.taxonomy,
            state=args.state,
            top=args.top,
        )
    else:
        candidates = load_providers(settings.reference_dir, CANDIDATES_FILE)
        chosen = rank_providers_by_code_coverage(
            settings.bronze_rates_path, candidates, top=args.top
        )
    write_providers(chosen, settings.reference_dir / PROVIDERS_FILE)
    for provider in chosen:
        print(f"{provider.npi} | {provider.name} | {provider.city} {provider.postal_code}")
    return 0 if chosen else 1


def cmd_sample_report(args: argparse.Namespace, settings: Settings) -> int:
    rates_path = Path(args.rates) if args.rates else settings.bronze_rates_path
    published = load_published_rates(rates_path)
    providers = load_providers(settings.reference_dir)
    targets = {provider.npi for provider in providers}
    if targets:
        published = published[published["npi"].isin(targets)]
    dataset = payment_generator.generate(published, seed=args.seed)
    payments_csv, answers_csv = payment_generator.write(dataset, settings.data_dir / "sample")
    result = run_check(
        payments_csv,
        settings,
        customer_name=SAMPLE_CUSTOMER,
        data_label=args.label,
        bronze_rates=rates_path,
        use_ai_letters=args.ai_letters,
        provider_labels=None if args.show_provider_ids else masked_labels(providers),
    )
    _print_result(result)
    print(f"Answer key: {answers_csv}")
    return 0


def cmd_check(args: argparse.Namespace, settings: Settings) -> int:
    result = run_check(
        Path(args.input),
        settings,
        customer_name=args.customer,
        data_label=args.label,
        use_ai_letters=args.ai_letters,
    )
    _print_result(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upc", description="Underpayment Checker")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list-rate-files", help="list in-network files in a payer index")
    listing.add_argument("--index", required=True)
    listing.add_argument("--keyword", default="")
    listing.add_argument("--limit", type=int, default=20)
    listing.set_defaults(handler=cmd_list_rate_files)

    download = commands.add_parser("download", help="resumable download of a rate file")
    download.add_argument("--url", required=True)
    download.add_argument("--dest", required=True)
    download.set_defaults(handler=cmd_download)

    find = commands.add_parser("find-providers", help="find providers in the NPPES registry")
    find.add_argument("--city", required=True)
    find.add_argument("--state", required=True)
    find.add_argument("--taxonomy", default="Physical Therapist")
    find.set_defaults(handler=cmd_find_providers)

    ingest = commands.add_parser("ingest-rates", help="stream a rate file into bronze parquet")
    ingest.add_argument("--source", required=True, help="local path or URL (.json or .json.gz)")
    ingest.add_argument("--payer", required=True)
    ingest.add_argument(
        "--all-providers",
        action="store_true",
        help="keep every provider, not only candidate/target NPIs",
    )
    ingest.set_defaults(handler=cmd_ingest_rates)

    select = commands.add_parser("select-providers", help="pick providers found in the rate file")
    select.add_argument("--top", type=int, default=5)
    select.add_argument(
        "--from-rate-file",
        action="store_true",
        help="start from providers in the rate file and look them up in NPPES",
    )
    select.add_argument("--taxonomy", default="Physical Therapist", help="taxonomy prefix")
    select.add_argument("--state", default="TX")
    select.set_defaults(handler=cmd_select_providers)

    sample = commands.add_parser(
        "sample-report", help="sample report: illustrative payments on real rates"
    )
    sample.add_argument("--rates", help="bronze rates parquet (default: data/bronze)")
    sample.add_argument("--seed", type=int, default=7)
    sample.add_argument("--label", default=SAMPLE_LABEL, help="data label printed on the report")
    sample.add_argument(
        "--show-provider-ids",
        action="store_true",
        help="show real NPIs instead of masked labels (never share such a sample report)",
    )
    sample.add_argument("--ai-letters", action="store_true", help="draft letters with Claude")
    sample.set_defaults(handler=cmd_sample_report)

    check = commands.add_parser("check", help="check a customer's payment totals")
    check.add_argument("--input", required=True)
    check.add_argument("--customer", required=True)
    check.add_argument("--label", default="customer payment totals, published rates")
    check.add_argument("--ai-letters", action="store_true", help="draft letters with Claude")
    check.set_defaults(handler=cmd_check)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.handler(args, Settings.from_env())
