# erp-crm-reconciliation-pipeline

[![CI](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/actions/workflows/ci.yml)
[![Pages](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/actions/workflows/pages.yml/badge.svg?branch=main)](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/actions/workflows/pages.yml)

📖 **[Read the full documentation](https://henrymbuguak.github.io/erp-crm-reconciliation-pipeline/)**

Synthetic **ERP + CRM dataset generator** for building and testing a
customer/invoice/payment reconciliation pipeline.

The `datagen` CLI produces two deliberately divergent exports of the *same*
underlying business data -- an ERP-style flat CSV export and a CRM-style
nested JSON export -- complete with realistic "messy data" defects (bad date
formats, missing values, mixed encodings, duplicate rows) and genuine
cross-system discrepancies (records existing in only one system, payment
amounts that legitimately differ between systems). A `ground_truth.json` can
optionally be emitted alongside the data, recording exactly which records
should reconcile, so a reconciliation pipeline's output can be scored for
precision/recall against a known-correct answer key.

## Why two divergent exports instead of one clean dataset?

A reconciliation pipeline is only as good as the messy data it's tested
against. Real ERP and CRM systems almost never agree on field names, ID
formats, or even which records exist -- that's exactly the kind of
divergence this tool reproduces on purpose:

| | ERP export | CRM export |
|---|---|---|
| Format | Flat CSV (`erp/customers.csv`, `erp/invoices.csv`, `erp/payments.csv`) | Nested JSON (`crm/customers.json`) |
| Field naming | Legacy `UPPER_SNAKE_CASE` (`CUST_ID`, `INV_NO`) | `camelCase` (`customerId`, `invoiceNumber`) |
| Business keys | `C000001`, `INV-000001`, `PMT-000001` | `CUST-000001`, `INV000001`, `PAY000001` |
| Structure | One row per invoice/payment | Invoices nested under customers; payments nested under invoices |

Both exports are projections of the same internal, seeded "ground truth"
entities (see [`src/datagen/identities.py`](src/datagen/identities.py)), so a
correct reconciliation pipeline should be able to match them back together
despite the different formats.

## Quickstart

This project uses [uv](https://docs.astral.sh/uv/) for dependency and
environment management.

```powershell
uv sync
uv run datagen generate --seed 42 --customers 200 --with-ground-truth --output-dir data
```

This writes:

```
data/
  erp/customers.csv
  erp/invoices.csv
  erp/payments.csv
  crm/customers.json
  ground_truth.json        # only with --with-ground-truth
  generation_config.yaml   # the exact config used, for reproducibility/audit
```

Re-running with the same `--seed` (and the same other options) always
reproduces byte-identical output.

### CLI reference

```powershell
uv run datagen --help
uv run datagen generate --help
uv run datagen show-config          # print the fully-resolved config as YAML
```

Key options on `generate` (all are overrides layered on top of `--config`,
if given, or on top of defaults otherwise):

| Option | Default | Meaning |
|---|---|---|
| `--seed` | 42 | Master RNG seed; same seed -> same dataset |
| `--customers` | 200 | Number of customers to generate |
| `--min-invoices` / `--max-invoices` | 1 / 5 | Invoices generated per customer |
| `--payment-coverage` | 0.85 | Fraction of eligible invoices that receive a payment |
| `--output-dir` | `data` | Where to write the export |
| `--config` | -- | Base config YAML (see below); other flags still override it |
| `--with-ground-truth` / `--no-ground-truth` | off | Emit `ground_truth.json` |
| `--missing-value-ratio`, `--bad-date-ratio`, `--encoding-issue-ratio`, `--duplicate-ratio`, `--orphan-ratio`, `--amount-drift-ratio` | see below | Messiness knobs (0.0-1.0) |

### Using a config file

```powershell
uv run datagen show-config > my-config.yaml   # start from the resolved defaults
uv run datagen generate --config my-config.yaml --output-dir data
```

Any `generate` flag you also pass on the command line overrides the
corresponding value from `--config`.

## A worked example

See [`examples/sample_dataset`](examples/sample_dataset) for a small,
committed dataset (8 customers, `--seed 1`) you can inspect without running
anything. It was generated with:

```powershell
uv run datagen generate --seed 1 --customers 8 --with-ground-truth --output-dir examples/sample_dataset
```

## Architecture

```
src/datagen/
  config.py           GenerationConfig / MessinessConfig (pydantic, YAML round-trippable)
  identities.py        Canonical ("ground truth") entity models
  rng.py                Seeded RNG helpers (independent, reproducible streams)
  keys.py               Business-facing ID formatting, divergent per system
  generators/           Faker/mimesis-based entity generation
    customers.py          Names, emails, addresses, phone numbers (Faker)
    invoices.py            Invoice amounts/currency/status (mimesis) + orphan decisions
    payments.py             Payments against invoices + ERP/CRM amount drift decisions
  messiness/            Cosmetic "messy data" injection (pandas-based, composable)
    dates.py               Inconsistent/invalid date formats
    encoding.py              Mojibake / mixed-encoding corruption
    missing.py                NaN / "N/A" / "--" / etc.
    duplicates.py              Near-duplicate rows (with minor perturbation)
    mismatches.py                Materializes ERP/CRM payment-amount drift at export time
  exporters/            System-specific projection + serialization
    erp_csv.py             Flat CSV, legacy field names
    crm_json.py              Nested JSON, camelCase field names
  ground_truth.py       Reconciliation answer-key mapping (JSON)
  cli.py                Typer CLI
```

**Design principle:** structural cross-system discrepancies (a record
existing in only one system, or a payment amount that legitimately differs
between systems) are decided once, in the generators, since they require
knowledge of *both* systems at once. Cosmetic messiness (bad date formats,
missing values, encoding issues, duplicate rows) is applied independently,
per export, in `messiness/` -- so the ERP and CRM copies of the same data
diverge realistically instead of being corrupted identically.

Reproducibility is achieved by deriving all randomness -- including internal
correlation UUIDs -- from a single master seed via
[`numpy.random.SeedSequence.spawn`](src/datagen/rng.py), rather than relying
on any OS-level randomness.

## Development

```powershell
uv sync --all-groups
uv run pytest              # 43 tests, ~95% coverage
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy                # strict type checking
uv run pre-commit install  # run the above automatically on every commit
```

CI (`.github/workflows/ci.yml`) runs the same checks on every push/PR.

### Documentation site

The full documentation (architecture diagrams, CLI reference, data model,
and an auto-generated API reference) is built with
[MkDocs Material](https://squidfunk.github.io/mkdocs-material/) and
published to GitHub Pages by `.github/workflows/pages.yml` on every push to
`main`. To preview it locally:

```powershell
uv sync --group docs
uv run mkdocs serve   # http://127.0.0.1:8000
```

### Local development network note

If your network blocks direct access to `files.pythonhosted.org` and
requires routing package downloads through an internal PyPI-compatible
mirror, copy [`uv.toml.example`](uv.toml.example) to `uv.toml` (gitignored)
and point it at your mirror. This mirrors the `.env` pattern: the override
is local-only and never affects other clones or CI, which resolve against
standard PyPI. `uv.lock` is likewise gitignored so a mirror-specific lock
never leaks into the shared repo -- each environment resolves its own lock
from `pyproject.toml`.
