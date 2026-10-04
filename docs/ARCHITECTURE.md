# Architecture

```
SOURCES                 BRONZE                                SILVER                     GOLD                  OUTPUT
Payer index (monthly) ─► payer_index_reader ─► select a rate file
Rate file (2.4 GB gz) ─► rate_file_streamer ─► published_rates ─► silver_published_rates ─┐
NPPES registry        ─► provider_registry_client ─► target providers                    ├─► gold_payment_gaps ─► PDF report
Customer totals (CSV) ─► customer_payment_totals_loader ─► silver_customer_payments ─────┘   gold_payer_summary ─► appeal letters
                                                                                                                ─► dashboard
```

## Facts for the design
The facts in this table were verified on 29 September 2026.

| Fact | Source |
|---|---|
| The BCBS Texas index `2026-08-20_..._index.json` lists 528 in-network files. The Blue Choice PPO file covers 94,549 plans. Its gzipped size is 2,431,534,267 bytes. | The live index and an HTTP HEAD request |
| In the real file, `provider_references` comes before `in_network`. Thus one parsing pass is sufficient. | The first part of the downloaded file |
| BCBS Texas does not publish rates by billing-code modifier. | BCBSTX MRF User Guide v1.4 (1 Feb 2026), section 3.2.1 |
| The place-of-service codes are present for professional rates. | BCBSTX guide, section 3.2 |
| A "derived" rate is an average from past claims (6-month lookback, minimum 6 claims). | BCBSTX guide, section 3.2.4 |
| The file writes each EIN with a dash, for example `76-0221050`. | The real file |
| "Always therapy" codes require a GP, GO or GN modifier. | CMS CY2026 Therapy Code List, disposition 5 |

## Matching rules (`gold_payment_gaps.sql`)
| Rule | Reason |
|---|---|
| Use only professional fee-for-service dollar rates (`negotiated`, `fee schedule`, `derived`). | A `percentage` rate is a percent of charges. Capitation and per diem rates are not prices for one service. |
| Use the rate for the exact modifier if it exists. If not, use the rate without a modifier. | BCBS Texas publishes no modifier rates. Therapy lines have the GP modifier. |
| Match the TIN and the place of service only when the customer gives them. | One NPI can have different rates for different TINs and places. |
| Ignore rates that expire before 1 January of the payment year. | Old rates do not apply. |
| The expected rate is the lowest candidate rate. | Each flag is then true for the least favourable reading. |
| Set HIGH confidence only for one exact dollar rate. | `derived` rates and multiple rates are estimates. They show as REVIEW. |
| Compare the allowed amount. Flag a row if the gap is more than 2 % and more than $50. | Deductibles and co-payments are not gaps. Small differences are noise. |

## Privacy
The customer input contains yearly totals. It has no patient fields, claim fields or service dates.
This agrees with HIPAA Safe Harbor de-identification (45 CFR 164.514(b)(2)). The loader rejects
columns that look like patient data. The appeal-letter function sends only aggregated findings to the
LLM. It never sends the customer file. Get a legal review of this approach before production use.

## Limits
- Network rate files are multi-gigabyte. The Blue Choice PPO file is 2.4 GB gzipped. Downloads can
  continue after a break, but they are slow on limited bandwidth.
- The pipeline gets remote provider references for each group. It does not keep a cache between runs.
- Customers must use the `payer_id` of this project, for example `BCBSTX`.
- The pipeline does not include Medicare fee-schedule prices.
