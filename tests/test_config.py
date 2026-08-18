"""Tests for GenerationConfig validation and YAML round-tripping."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from datagen.config import GenerationConfig, MessinessConfig


def test_defaults_are_valid() -> None:
    config = GenerationConfig()
    assert config.seed == 42
    assert config.num_customers == 200
    assert isinstance(config.messiness, MessinessConfig)


def test_invoice_range_validation() -> None:
    with pytest.raises(ValidationError):
        GenerationConfig(min_invoices_per_customer=5, max_invoices_per_customer=1)


@pytest.mark.parametrize("bad_ratio", [-0.1, 1.1])
def test_messiness_ratio_bounds(bad_ratio: float) -> None:
    with pytest.raises(ValidationError):
        MessinessConfig(missing_value_ratio=bad_ratio)


def test_yaml_round_trip(tmp_path: Path) -> None:
    config = GenerationConfig(seed=99, num_customers=10)
    path = tmp_path / "config.yaml"
    config.to_yaml(path)

    loaded = GenerationConfig.from_yaml(path)
    assert loaded == config


def test_from_yaml_uses_defaults_for_omitted_fields(tmp_path: Path) -> None:
    path = tmp_path / "partial.yaml"
    path.write_text("seed: 7\n", encoding="utf-8")

    loaded = GenerationConfig.from_yaml(path)
    assert loaded.seed == 7
    assert loaded.num_customers == 200  # default preserved
