"""Command-line interface for running the ERP/CRM reconciliation pipeline.

This CLI never reads `ground_truth.json` -- per CLAUDE.md's eval-only rule,
that file is only ever consulted by `eval/score.py` or tests. Precision/
recall is therefore never part of this CLI's report; run `eval/score.py`
separately against a dataset generated with `--with-ground-truth` for that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pipeline.crosswalk import upsert_crosswalk
from pipeline.models import CrosswalkEntry, EntityType
from pipeline.orchestrate import PipelineResult, run_pipeline
from pipeline.quarantine import write_quarantine_log
from pipeline.report import render_report, write_report
from pipeline.resolve import CUSTOMER_MATCH_THRESHOLD

app = typer.Typer(
    help="Ingest, clean, and reconcile ERP/CRM datasets into a crosswalk and Markdown report.",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    data_dir: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            help="Directory containing erp/ (CSV) and crm/ (JSON) subdirectories.",
        ),
    ],
    crosswalk_path: Annotated[
        Path,
        typer.Option(help="Where to upsert the crosswalk JSON (existing entries are preserved)."),
    ] = Path("data/processed/crosswalk.json"),
    quarantine_path: Annotated[
        Path, typer.Option(help="Where to write the quarantine log JSON.")
    ] = Path("data/processed/quarantine_log.json"),
    report_path: Annotated[
        Path, typer.Option(help="Where to write the Markdown reconciliation report.")
    ] = Path("RECONCILIATION_REPORT.md"),
    customer_threshold: Annotated[
        float, typer.Option(help="Confidence threshold for customer entity resolution.")
    ] = CUSTOMER_MATCH_THRESHOLD,
    postgres_dsn: Annotated[
        str | None,
        typer.Option(
            help="If set, also load the run into this Postgres DSN (see pipeline.postgres)."
        ),
    ] = None,
) -> None:
    """Run ingest -> dedupe -> clean -> resolve over DATA_DIR and write the crosswalk/report."""
    result = run_pipeline(data_dir, customer_match_threshold=customer_threshold)

    merged_crosswalk = upsert_crosswalk(result.crosswalk, crosswalk_path)
    write_quarantine_log(result.quarantine, quarantine_path)

    report = render_report(
        ingest_counts=result.ingest_counts,
        crosswalk=result.crosswalk,
        quarantine=result.quarantine,
        erp_payments=result.erp_payments,
        crm_payments=result.crm_payments,
    )
    write_report(report, report_path)

    _print_summary(result, merged_crosswalk, report_path, crosswalk_path, quarantine_path)

    if postgres_dsn is not None:
        _load_postgres(result, postgres_dsn)


def _load_postgres(result: PipelineResult, dsn: str) -> None:
    import psycopg

    from pipeline.postgres import load_pipeline_result

    with psycopg.connect(dsn) as conn:
        load_pipeline_result(conn, result)
    console.print("Loaded run into [bold]Postgres[/bold]")


def _print_summary(
    result: PipelineResult,
    merged_crosswalk: list[CrosswalkEntry],
    report_path: Path,
    crosswalk_path: Path,
    quarantine_path: Path,
) -> None:
    table = Table(title="Match rate by entity type")
    table.add_column("Entity")
    table.add_column("Matched", justify="right")
    table.add_column("Total", justify="right")
    for entity_type in EntityType:
        entries = [entry for entry in result.crosswalk if entry.entity_type == entity_type]
        matched = sum(
            1 for entry in entries if entry.erp_key is not None and entry.crm_key is not None
        )
        table.add_row(entity_type.value, str(matched), str(len(entries)))
    console.print(table)

    console.print(f"Quarantined records: {len(result.quarantine)}")
    console.print(f"Report written to [bold]{report_path}[/bold]")
    console.print(
        f"Crosswalk written to [bold]{crosswalk_path}[/bold] ({len(merged_crosswalk)} total entries)"
    )
    console.print(f"Quarantine log written to [bold]{quarantine_path}[/bold]")


if __name__ == "__main__":
    app()
