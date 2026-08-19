# ERP/CRM reconciliation pipeline

Generate realistic, deliberately messy synthetic ERP and CRM exports, and
reconcile them back into a single source of truth.

[Get started](getting-started.md){ .md-button .md-button--primary }
[Explore the architecture](architecture.md){ .md-button }

## What the repository demonstrates

- Synthetic customer/invoice/payment generation with [Faker](https://faker.readthedocs.io/) and [mimesis](https://mimesis.name/), fully reproducible from a single seed.
- Two deliberately divergent exports of the same underlying data: an ERP-style flat CSV using legacy field names, and a CRM-style nested JSON using camelCase field names -- mirroring how a real SAP/Salesforce-style hybrid legacy stack disagrees with itself.
- Composable "messy data" injection: inconsistent/invalid date formats, mixed-encoding corruption, missing values, and near-duplicate rows, applied independently per export.
- Genuine cross-system discrepancies -- orphan records and legitimate ERP/CRM amount drift -- with an optional `ground_truth.json` answer key for scoring a downstream reconciliation pipeline's precision/recall.
- A [Typer](https://typer.tiangolo.com/) CLI, a `pydantic`-validated, YAML-round-trippable configuration model, and a fully typed (`mypy --strict`) codebase with ~95% test coverage.

## Choose a path

| Goal                                   | Start here                                                                          |
| --------------------------------------- | ------------------------------------------------------------------------------------ |
| Generate a dataset and inspect the CLI | [Get started](getting-started.md)                                                     |
| Understand how the pieces fit together | [Architecture](architecture.md)                                                      |
| Look up CLI flags or the data schema   | [Reference](reference/cli.md)                                                        |
| Inspect the implementation             | [Repository on GitHub](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline) |

!!! note "Part of a larger project"
    Dataset generation is the foundation for a broader **Legacy ERP/CRM
    Integration and Data Cleaning Pipeline**: an ingestion and cleaning engine
    (Polars + Pydantic), a quarantine system for invalid rows, entity
    resolution between the ERP and CRM record sets, and a stakeholder-facing
    reconciliation report. Those pieces build directly on the datasets and
    ground-truth mapping generated here.
