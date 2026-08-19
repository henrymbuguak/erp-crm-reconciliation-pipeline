# Getting started

This project uses [uv](https://docs.astral.sh/uv/) for dependency and
environment management.

## Install and generate a dataset

```bash
uv sync
uv run datagen generate --seed 42 --customers 200 --with-ground-truth --output-dir data
```

This writes:

```text
data/
  erp/customers.csv
  erp/invoices.csv
  erp/payments.csv
  crm/customers.json
  ground_truth.json        # only with --with-ground-truth
  generation_config.yaml   # the exact config used, for reproducibility/audit
```

Re-running with the same `--seed` and other options always reproduces
byte-identical output -- every source of randomness, including internal
correlation UUIDs, derives from a single master seed.

## CLI reference

```bash
uv run datagen --help
uv run datagen generate --help
uv run datagen show-config          # print the fully-resolved config as YAML
```

See the [CLI reference](reference/cli.md) for the full flag list, and the
[data model reference](reference/data-model.md) for how ERP and CRM field
names/formats diverge.

## Using a config file

```bash
uv run datagen show-config > my-config.yaml   # start from the resolved defaults
uv run datagen generate --config my-config.yaml --output-dir data
```

Any `generate` flag also passed on the command line overrides the
corresponding value from `--config`.

## A worked example

See [`examples/sample_dataset`](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/tree/main/examples/sample_dataset)
in the repository for a small, committed dataset (8 customers, `--seed 1`)
you can inspect without running anything.

## Reconcile the data

Once you have a generated dataset, run the reconciliation pipeline over it:

```bash
uv run reconcile data
```

This ingests `data/erp/*.csv` and `data/crm/customers.json`, cleans and
validates every row, resolves ERP records against CRM records, and writes:

```text
data/processed/crosswalk.json        # upserted on every run, never overwritten
data/processed/quarantine_log.json   # every row that failed cleaning/validation, or tied on resolution
RECONCILIATION_REPORT.md             # match rate, quarantine breakdown, orphans, payment drift
```

Re-running `reconcile` on the same input is idempotent: existing crosswalk
entries are kept and only genuinely new ones are appended.

If you generated the dataset `--with-ground-truth`, score the pipeline's
matcher against it (precision/recall/F1) with:

```bash
uv run python -m eval.score data --threshold 0.75
```

`eval/score.py` is the only place `ground_truth.json` is ever read --
`reconcile` itself never consults it. See the [CLI reference](reference/cli.md#reconcile)
for the full flag list, and the [data model reference](reference/data-model.md#pipeline-data-model)
for the pipeline's clean-record schemas, crosswalk, and quarantine format.

## Development

```bash
uv sync --all-groups
uv run pytest              # 107 tests, ~96% coverage (datagen + pipeline)
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy                # strict type checking
uv run pre-commit install  # run the above automatically on every commit
```

### Local development network note

If your network blocks direct access to `files.pythonhosted.org` and
requires routing package downloads through an internal PyPI-compatible
mirror, copy `uv.toml.example` (in the repository root) to `uv.toml`
(gitignored) and point it at your mirror. `uv.lock` is likewise gitignored
so a mirror-specific lock never leaks into the shared repo -- each
environment resolves its own lock from `pyproject.toml`.

Because `uv.toml` is gitignored, `git worktree` doesn't share it: only
Git-tracked files are common across worktrees, so copy it into each
worktree of this repo that needs it.
