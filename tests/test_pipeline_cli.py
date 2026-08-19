"""End-to-end tests for `pipeline.cli`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app

runner = CliRunner()

SAMPLE_DATASET = Path(__file__).parent.parent / "examples" / "sample_dataset"


def test_run_writes_crosswalk_quarantine_and_report(tmp_path: Path) -> None:
    crosswalk_path = tmp_path / "crosswalk.json"
    quarantine_path = tmp_path / "quarantine_log.json"
    report_path = tmp_path / "RECONCILIATION_REPORT.md"

    result = runner.invoke(
        app,
        [
            str(SAMPLE_DATASET),
            "--crosswalk-path",
            str(crosswalk_path),
            "--quarantine-path",
            str(quarantine_path),
            "--report-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert crosswalk_path.exists()
    assert quarantine_path.exists()
    assert report_path.exists()

    crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    assert len(crosswalk) > 0

    report = report_path.read_text(encoding="utf-8")
    assert "# Reconciliation Report" in report
    # This CLI never reads ground_truth.json, so precision/recall is never in its report.
    assert "Precision / recall" not in report


def test_run_upserts_into_existing_crosswalk(tmp_path: Path) -> None:
    crosswalk_path = tmp_path / "crosswalk.json"
    quarantine_path = tmp_path / "quarantine_log.json"
    report_path = tmp_path / "RECONCILIATION_REPORT.md"

    args = [
        str(SAMPLE_DATASET),
        "--crosswalk-path",
        str(crosswalk_path),
        "--quarantine-path",
        str(quarantine_path),
        "--report-path",
        str(report_path),
    ]

    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.stdout
    first_crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))

    second = runner.invoke(app, args)
    assert second.exit_code == 0, second.stdout
    second_crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))

    # Re-running on unchanged input must not duplicate crosswalk entries.
    assert len(second_crosswalk) == len(first_crosswalk)
