"""Command-line interface for generating synthetic ERP/CRM datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.table import Table

from datagen.config import GenerationConfig
from datagen.exporters.crm_json import export_crm_json
from datagen.exporters.erp_csv import export_erp_csv
from datagen.generators.customers import generate_customers
from datagen.generators.invoices import generate_invoices
from datagen.generators.payments import generate_payments
from datagen.ground_truth import build_ground_truth, write_ground_truth

app = typer.Typer(
    help="Generate messy synthetic ERP (CSV) and CRM (JSON) datasets for reconciliation-pipeline testing.",
    add_completion=False,
)
console = Console()


@app.command()
def generate(
    seed: Annotated[
        int | None,
        typer.Option(
            help="Override: master RNG seed; the same seed always reproduces the same dataset."
        ),
    ] = None,
    customers: Annotated[
        int | None, typer.Option(help="Override: number of customers to generate.")
    ] = None,
    min_invoices: Annotated[
        int | None, typer.Option(help="Override: minimum invoices per customer.")
    ] = None,
    max_invoices: Annotated[
        int | None, typer.Option(help="Override: maximum invoices per customer.")
    ] = None,
    payment_coverage: Annotated[
        float | None, typer.Option(help="Override: fraction of invoices that receive a payment.")
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            help="Override: directory to write erp/, crm/, and optional ground truth into.",
        ),
    ] = None,
    config_file: Annotated[
        Path | None,
        typer.Option(
            "--config",
            exists=True,
            help="Base YAML GenerationConfig; any other flag passed overrides it.",
        ),
    ] = None,
    with_ground_truth: Annotated[
        bool | None,
        typer.Option(
            "--with-ground-truth/--no-ground-truth",
            help="Override: also emit ground_truth.json for validating reconciliation results.",
        ),
    ] = None,
    missing_value_ratio: Annotated[
        float | None,
        typer.Option(help="Override: fraction of cells replaced with missing markers."),
    ] = None,
    bad_date_ratio: Annotated[
        float | None,
        typer.Option(help="Override: fraction of dates rewritten inconsistently/invalidly."),
    ] = None,
    encoding_issue_ratio: Annotated[
        float | None, typer.Option(help="Override: fraction of text cells corrupted with mojibake.")
    ] = None,
    duplicate_ratio: Annotated[
        float | None, typer.Option(help="Override: fraction of rows duplicated per export.")
    ] = None,
    orphan_ratio: Annotated[
        float | None,
        typer.Option(help="Override: fraction of invoices/payments existing in only one system."),
    ] = None,
    amount_drift_ratio: Annotated[
        float | None,
        typer.Option(help="Override: fraction of payments with an ERP/CRM amount mismatch."),
    ] = None,
) -> None:
    """Generate a full synthetic ERP + CRM dataset (customers, invoices, payments).

    Without ``--config``, generation uses :class:`~datagen.config.GenerationConfig`
    defaults. Any other flag that is explicitly passed always overrides the
    base config (whether that base came from defaults or ``--config``), so
    ``--config base.yaml --output-dir out2/`` behaves as expected.
    """
    config = (
        GenerationConfig.from_yaml(config_file) if config_file is not None else GenerationConfig()
    )

    top_level_overrides = {
        "seed": seed,
        "num_customers": customers,
        "min_invoices_per_customer": min_invoices,
        "max_invoices_per_customer": max_invoices,
        "payment_coverage_ratio": payment_coverage,
        "output_dir": output_dir,
        "with_ground_truth": with_ground_truth,
    }
    active_top_level_overrides = {k: v for k, v in top_level_overrides.items() if v is not None}
    if active_top_level_overrides:
        config = GenerationConfig.model_validate(
            {**config.model_dump(), **active_top_level_overrides}
        )

    messiness_overrides = {
        "missing_value_ratio": missing_value_ratio,
        "bad_date_ratio": bad_date_ratio,
        "encoding_issue_ratio": encoding_issue_ratio,
        "duplicate_ratio": duplicate_ratio,
        "orphan_ratio": orphan_ratio,
        "amount_drift_ratio": amount_drift_ratio,
    }
    active_messiness_overrides = {k: v for k, v in messiness_overrides.items() if v is not None}
    if active_messiness_overrides:
        config.messiness = config.messiness.model_copy(update=active_messiness_overrides)
        config = GenerationConfig.model_validate(config.model_dump())

    with console.status("[bold green]Generating synthetic data..."):
        customer_records = generate_customers(config.num_customers, config.seed)
        invoice_records = generate_invoices(customer_records, config, config.seed)
        payment_records = generate_payments(invoice_records, config, config.seed)

        config.output_dir.mkdir(parents=True, exist_ok=True)
        export_erp_csv(
            customer_records,
            invoice_records,
            payment_records,
            config,
            config.seed,
            config.output_dir,
        )
        export_crm_json(
            customer_records,
            invoice_records,
            payment_records,
            config,
            config.seed,
            config.output_dir,
        )

        if config.with_ground_truth:
            ground_truth = build_ground_truth(invoice_records, payment_records)
            write_ground_truth(ground_truth, config.output_dir / "ground_truth.json")

        config.to_yaml(config.output_dir / "generation_config.yaml")

    table = Table(title="Dataset generated")
    table.add_column("Entity")
    table.add_column("Count", justify="right")
    table.add_row("Customers", str(len(customer_records)))
    table.add_row("Invoices", str(len(invoice_records)))
    table.add_row("Payments", str(len(payment_records)))
    console.print(table)
    console.print(f"[bold]Output directory:[/bold] {config.output_dir.resolve()}")
    console.print("  erp/customers.csv, erp/invoices.csv, erp/payments.csv")
    console.print("  crm/customers.json")
    if config.with_ground_truth:
        console.print("  ground_truth.json")
    console.print("  generation_config.yaml  (records the exact config used, for reproducibility)")


@app.command("show-config")
def show_config(
    config_file: Annotated[
        Path | None,
        typer.Option("--config", exists=True, help="YAML config to resolve instead of defaults."),
    ] = None,
) -> None:
    """Print the fully-resolved GenerationConfig as YAML, without generating anything."""
    config = (
        GenerationConfig.from_yaml(config_file) if config_file is not None else GenerationConfig()
    )
    console.print(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))


if __name__ == "__main__":
    app()
