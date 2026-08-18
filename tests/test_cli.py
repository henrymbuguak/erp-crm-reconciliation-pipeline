"""End-to-end tests for the Typer CLI."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from datagen.cli import app

runner = CliRunner()


def test_show_config_prints_valid_yaml() -> None:
    result = runner.invoke(app, ["show-config"])
    assert result.exit_code == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["seed"] == 42
    assert parsed["num_customers"] == 200


def test_generate_writes_expected_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "generate",
            "--seed",
            "1",
            "--customers",
            "5",
            "--output-dir",
            str(output_dir),
            "--with-ground-truth",
        ],
    )
    assert result.exit_code == 0, result.stdout

    assert (output_dir / "erp" / "customers.csv").exists()
    assert (output_dir / "erp" / "invoices.csv").exists()
    assert (output_dir / "erp" / "payments.csv").exists()
    assert (output_dir / "crm" / "customers.json").exists()
    assert (output_dir / "ground_truth.json").exists()
    assert (output_dir / "generation_config.yaml").exists()

    ground_truth = json.loads((output_dir / "ground_truth.json").read_text(encoding="utf-8"))
    assert "summary" in ground_truth


def test_generate_is_reproducible_across_runs(tmp_path: Path) -> None:
    out1, out2 = tmp_path / "run1", tmp_path / "run2"
    for out in (out1, out2):
        result = runner.invoke(
            app, ["generate", "--seed", "5", "--customers", "5", "--output-dir", str(out)]
        )
        assert result.exit_code == 0

    assert (out1 / "erp" / "customers.csv").read_text() == (
        out2 / "erp" / "customers.csv"
    ).read_text()
    assert (out1 / "crm" / "customers.json").read_text() == (
        out2 / "crm" / "customers.json"
    ).read_text()


def test_generate_with_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("seed: 3\nnum_customers: 4\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    result = runner.invoke(
        app, ["generate", "--config", str(config_path), "--output-dir", str(output_dir)]
    )
    assert result.exit_code == 0, result.stdout
    assert (output_dir / "erp" / "customers.csv").exists()
