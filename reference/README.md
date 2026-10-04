# Reference data

| File | Source |
|---|---|
| `target_codes.csv` | CMS CY2026 Therapy Code List (`2026-therapy-code-list-dispositions.zip`, Annual Therapy Update page on cms.gov). The list keeps the active 97xxx codes with disposition 5 ("always therapy") or 9 (evaluations). It removes disposition 1 (contractor-priced) and disposition 3 (bundled; never paid separately). |
| `payers.csv` | The BCBS Texas table-of-contents URL from bcbstx.com/member/machine-readable-files. The index date is 2026-08-20. |
| `target_providers.csv` | The command `upc select-providers` makes this file. It lists providers that are in the BCBS Texas rate file. The names come from the public NPPES registry. Git does not track this file. |
