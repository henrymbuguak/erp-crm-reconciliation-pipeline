# ERP/CRM reconciliation pipeline

[![CI](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/actions/workflows/ci.yml)
[![Pages](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/actions/workflows/pages.yml/badge.svg?branch=main)](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/actions/workflows/pages.yml)

📖 **[Read the full documentation](https://henrymbuguak.github.io/erp-crm-reconciliation-pipeline/)**

A two-part project for testing legacy data migrations: a synthetic
**Enterprise Resource Planning (ERP) and Customer Relationship Management
(CRM) dataset generator**, and a **reconciliation pipeline** that ingests,
cleans, and matches the two systems' records back together.

**Step 1 -- `datagen`:** produces two deliberately divergent exports of the
_same_ underlying business data: an ERP-style flat CSV export and a
CRM-style nested JSON export, complete with realistic "messy data" defects
(bad date formats, missing values, mixed encodings, duplicate rows) and
genuine cross-system discrepancies -- records existing in only one system,
and payment amounts that legitimately differ between systems. You can
optionally emit a `ground_truth.json` alongside the data, recording exactly
which records should reconcile, so you can score a reconciliation
pipeline's output for precision and recall against a known-correct answer
key.

**Step 2 -- `pipeline` (the `reconcile` CLI):** ingests both exports with
Polars, repairs recoverable messiness, validates every row against Pydantic
schemas, resolves ERP records against CRM records (by name/email/phone and
date/amount proximity -- never by business-key format), and writes a
crosswalk plus a Markdown reconciliation report.

## Why two divergent exports instead of one clean dataset?

A reconciliation pipeline is only as good as the messy data it's tested
against. Real ERP and CRM systems almost never agree on field names, ID
formats, or even which records exist -- that's exactly the kind of
divergence `datagen` reproduces on purpose:

|               | ERP export                                                             | CRM export                                                      |
| ------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------- |
| Format        | Flat CSV (`erp/customers.csv`, `erp/invoices.csv`, `erp/payments.csv`) | Nested JSON (`crm/customers.json`)                              |
| Field naming  | Legacy `UPPER_SNAKE_CASE` (`CUST_ID`, `INV_NO`)                        | `camelCase` (`customerId`, `invoiceNumber`)                     |
| Business keys | `C000001`, `INV-000001`, `PMT-000001`                                  | `CUST-000001`, `INV000001`, `PAY000001`                         |
| Structure     | One row per invoice/payment                                            | Invoices nest under customers, and payments nest under invoices |

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
uv run reconcile data
```

The first command writes:

```
data/
  erp/customers.csv
  erp/invoices.csv
  erp/payments.csv
  crm/customers.json
  ground_truth.json        # only with --with-ground-truth
  generation_config.yaml   # the exact config used, for reproducibility/audit
```

Re-running with the same `--seed` and other options always reproduces
byte-identical output.

The second command ingests that data and writes:

```
data/processed/crosswalk.json        # upserted on every run, never overwritten
data/processed/quarantine_log.json   # every row that failed cleaning/validation, or tied on resolution
RECONCILIATION_REPORT.md             # match rate, quarantine breakdown, orphans, payment drift
```

If you generated the dataset `--with-ground-truth`, score the pipeline's
matcher against it (`reconcile` itself never reads `ground_truth.json` --
see [Hard constraints](#hard-constraints) below):

```powershell
uv run python -m eval.score data --threshold 0.75
```

### CLI reference

```powershell
uv run datagen --help
uv run datagen generate --help
uv run datagen show-config          # print the fully-resolved config as YAML
uv run reconcile --help
```

Key options on `datagen generate` (all are overrides layered on top of
`--config`, if given, or on top of defaults otherwise):

| Option                                                                                                                               | Default   | Meaning                                                            |
| ------------------------------------------------------------------------------------------------------------------------------------ | --------- | ------------------------------------------------------------------ |
| `--seed`                                                                                                                             | 42        | Master RNG seed -- the same seed always produces the same dataset  |
| `--customers`                                                                                                                        | 200       | Number of customers to generate                                    |
| `--min-invoices` / `--max-invoices`                                                                                                  | 1 / 5     | Invoices generated per customer                                    |
| `--payment-coverage`                                                                                                                 | 0.85      | Fraction of eligible invoices that receive a payment               |
| `--output-dir`                                                                                                                       | `data`    | Where to write the export                                          |
| `--config`                                                                                                                           | --        | Base config YAML, described below -- other flags still override it |
| `--with-ground-truth` / `--no-ground-truth`                                                                                          | off       | Emit `ground_truth.json`                                           |
| `--missing-value-ratio`, `--bad-date-ratio`, `--encoding-issue-ratio`, `--duplicate-ratio`, `--orphan-ratio`, `--amount-drift-ratio` | see below | Messiness knobs (0.0-1.0)                                          |

Key options on `reconcile`:

| Option                  | Default                              | Meaning                                                            |
| ----------------------- | ------------------------------------ | ------------------------------------------------------------------ |
| `data_dir` (positional) | --                                   | Directory containing `erp/` (CSV) and `crm/` (JSON) subdirectories |
| `--crosswalk-path`      | `data/processed/crosswalk.json`      | Upserted (never overwritten) crosswalk output                      |
| `--quarantine-path`     | `data/processed/quarantine_log.json` | Quarantined-record log                                             |
| `--report-path`         | `RECONCILIATION_REPORT.md`           | Markdown reconciliation report                                     |
| `--customer-threshold`  | 0.75                                 | Confidence threshold for customer entity resolution                |

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
anything. The following command created it:

```powershell
uv run datagen generate --seed 1 --customers 8 --with-ground-truth --output-dir examples/sample_dataset
```

## Hard constraints

These rules (from `CLAUDE.md`, which governs the pipeline) shape the
implementation and are worth knowing before reading the code:

- **No ID-format shortcuts.** `CUST_ID` and `customerId` are cosmetically
  different encodings of the same sequence number only because this is a
  synthetic dataset. Entity resolution never parses, strips, or reverses
  business-key formats to align records across systems -- it matches on
  name/email/phone (customers) and date/amount proximity within an
  already-resolved parent (invoices, payments), the same signals a real
  migration would have.
- **`ground_truth.json` is eval-only.** It is never imported, read, or
  referenced by any module under `src/pipeline/`. Only `eval/score.py` (or
  tests) may read it -- see [`eval/score.py`](eval/score.py).
- **Zero silent failures.** Every row that fails cleaning/validation, or
  ties on entity resolution, is written to `quarantine_log.json` with a
  reason code -- never silently dropped. A genuine orphan (a record with no
  counterpart in the other system) is a valid outcome, not a failure, and
  is never quarantined.

## `CLAUDE.md`: the spec that governs the pipeline

[`CLAUDE.md`](CLAUDE.md) is a written specification for the `pipeline`
package, produced _before_ any pipeline code, that pins down the business
rules a real reconciliation project lives or dies on -- the kind of
decisions that are easy to leave implicit and get wrong:

- **Four resolution outcomes, not two.** A record either matches, is a
  genuine one-sided orphan, is ambiguous (tied candidates -- never guess),
  or is invalid (failed cleaning). Collapsing "orphan" into "quarantine"
  would make a normal, two-system dataset look like a broken pipeline in
  the final report.
- **Concrete, derived thresholds.** Match tolerances (date proximity, the
  amount-drift epsilon, the fuzzy-match confidence cutoff) are grounded in
  how `datagen` actually generates data, not guessed round numbers -- see
  [`docs/reference/data-model.md`](https://henrymbuguak.github.io/erp-crm-reconciliation-pipeline/reference/data-model/).
- **An explicit instruction to stop and ask.** When a business rule is
  genuinely ambiguous, the spec says to surface that ambiguity instead of
  picking a silent default.

Keeping this contract in one file paid off directly: while rewriting the
docs, an earlier draft of
[`docs/architecture.md`](https://henrymbuguak.github.io/erp-crm-reconciliation-pipeline/architecture/)
claimed entity resolution normalized business-key IDs across systems --
which directly contradicts the "no ID-format shortcuts" rule above and
isn't what `resolve.py` actually does. Having the rule written down made
that contradiction checkable, not a matter of re-reading the
implementation and hoping to notice.

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
  cli.py                Typer CLI (`datagen`)

src/pipeline/
  models.py             CleanCustomer/Invoice/Payment, QuarantineEntry, CrosswalkEntry, ReasonCode
  ingest.py              Reads raw ERP CSV / CRM JSON into polars DataFrames
  cleaners/
    duplicates.py          Collapses intra-system near-duplicate rows
    dates.py                 Parses every known date format the generator can produce
    encoding.py                Repairs mojibake back to UTF-8
    missing.py                  Per-field missing-value policy (quarantine vs. null)
  validate.py            Pydantic validation into Clean* models or a QuarantineEntry
  resolve.py             Entity resolution: customers (fuzzy), invoices/payments (exact + proximity)
  crosswalk.py           Idempotent crosswalk persistence (JSON, primary; upserted)
  quarantine.py          Quarantine log persistence (JSON)
  postgres.py            Optional Postgres target schema, loaded via `reconcile --postgres-dsn`
  report.py              Markdown reconciliation report
  orchestrate.py         Shared ingest -> dedupe -> validate -> resolve sequence
  cli.py                 Typer CLI (`reconcile`)

eval/
  score.py               The only module allowed to read ground_truth.json --
                          precision/recall/F1, never consulted at runtime by src/pipeline/
```

**Design principle (datagen):** the generators decide structural
cross-system discrepancies once -- for example, a record existing in only
one system, or a payment amount that legitimately differs between systems
-- because that decision requires knowledge of both systems at once. The
`messiness/` package then applies cosmetic messiness (bad date formats,
missing values, encoding issues, duplicate rows) independently per export,
so the ERP and CRM copies of the same data diverge realistically instead of
matching each other's corruption exactly.

All randomness -- including internal correlation UUIDs -- derives from a
single master seed via
[`numpy.random.SeedSequence.spawn`](src/datagen/rng.py), so reproducibility
doesn't depend on any OS-level randomness.

See [Architecture](https://henrymbuguak.github.io/erp-crm-reconciliation-pipeline/architecture/)
in the full documentation for module-level diagrams of both stages.

## Development

```powershell
uv sync --all-groups
uv run pytest              # 107 tests, ~96% coverage (datagen + pipeline)
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy                # strict type checking
uv run pre-commit install  # run the above automatically on every commit
```

`.github/workflows/ci.yml` runs the same checks on every push and pull
request.

### Documentation style

Prose in `README.md` and `docs/**/*.md` follows the [Google developer
documentation style guide](https://developers.google.com/style/), enforced
by [Vale](https://vale.sh/) with the community-maintained
[Google style package](https://github.com/errata-ai/Google) (not affiliated
with or endorsed by Google). This project deliberately overrides two rules
for its domain, documented in `.vale/styles/Project/`: it keeps "CLI"
instead of Google's suggested "command-line tool," and it doesn't treat
"camelCase" as jargon, since both are standard, unambiguous vocabulary for
its developer audience. Check your writing locally:

```powershell
choco install vale   # or see https://vale.sh/docs/install for other platforms
vale sync
vale README.md docs
```

CI runs the same check on every push and pull request.

### Documentation site

[MkDocs Material](https://squidfunk.github.io/mkdocs-material/) builds the
full documentation -- architecture diagrams, CLI reference, data model, and
an auto-generated API reference -- and `.github/workflows/pages.yml`
publishes it to GitHub Pages on every push to `main`. To preview it
locally:

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

Because `uv.toml` is gitignored, it isn't shared by `git worktree`: only
Git-tracked files are common across worktrees, so each worktree of this
repo needs its own copy. If `uv sync` in a given worktree tries to reach
`files.pythonhosted.org` directly instead of your mirror, that's the
usual cause -- copy `uv.toml.example` to `uv.toml` in that worktree too.
