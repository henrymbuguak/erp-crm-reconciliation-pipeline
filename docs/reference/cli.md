# CLI reference

```bash
uv run datagen --help
```

## `datagen generate`

Generate a full synthetic ERP + CRM dataset (customers, invoices, payments).
Every flag below is an override layered on top of `--config` (if given) or
on top of defaults otherwise.

| Option                                      | Default | Meaning                                                           |
| ------------------------------------------- | ------- | ----------------------------------------------------------------- |
| `--seed`                                    | 42      | Master RNG seed -- the same seed always produces the same dataset |
| `--customers`                               | 200     | Number of customers to generate                                   |
| `--min-invoices` / `--max-invoices`         | 1 / 5   | Invoices generated per customer                                   |
| `--payment-coverage`                        | 0.85    | Fraction of eligible invoices that receive a payment              |
| `--output-dir`                              | `data`  | Where to write the export                                         |
| `--config`                                  | --      | Base config YAML -- other flags still override it                 |
| `--with-ground-truth` / `--no-ground-truth` | off     | Emit `ground_truth.json`                                          |
| `--missing-value-ratio`                     | 0.05    | Fraction of cells replaced with missing-value markers             |
| `--bad-date-ratio`                          | 0.08    | Fraction of dates rewritten inconsistently/invalidly              |
| `--encoding-issue-ratio`                    | 0.03    | Fraction of text cells corrupted with mojibake                    |
| `--duplicate-ratio`                         | 0.02    | Fraction of rows duplicated per export                            |
| `--orphan-ratio`                            | 0.05    | Fraction of invoices/payments existing in only one system         |
| `--amount-drift-ratio`                      | 0.04    | Fraction of payments with a legitimate ERP/CRM amount mismatch    |

## `datagen show-config`

Prints the fully resolved `GenerationConfig` as YAML, without generating
anything. Useful as a starting point for a `--config` file:

```bash
uv run datagen show-config > my-config.yaml
```

## `reconcile`

Runs the reconciliation pipeline (ingest -> dedupe -> clean/validate ->
resolve) over a data directory and writes the crosswalk, quarantine log, and
Markdown report.

```bash
uv run reconcile data/raw
```

| Option                  | Default                              | Meaning                                                                                                |
| ----------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `data_dir` (positional) | --                                   | Directory containing `erp/` (CSV) and `crm/` (JSON) subdirectories                                     |
| `--crosswalk-path`      | `data/processed/crosswalk.json`      | Upserted (never overwritten) crosswalk output                                                          |
| `--quarantine-path`     | `data/processed/quarantine_log.json` | Quarantined-record log                                                                                 |
| `--report-path`         | `RECONCILIATION_REPORT.md`           | Markdown reconciliation report                                                                         |
| `--customer-threshold`  | `resolve.CUSTOMER_MATCH_THRESHOLD`   | Confidence threshold for customer matching                                                             |
| `--postgres-dsn`        | --                                   | If set, also load the run into this Postgres DSN (see [`pipeline.postgres`](api.md#pipeline.postgres)) |

This CLI never reads `ground_truth.json`; precision/recall against ground
truth is only ever computed by `eval/score.py`:

```bash
uv run python -m eval.score data/raw
```
