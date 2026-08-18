"""Configuration models for synthetic ERP/CRM data generation.

All generation behavior (volume, RNG seed, and "messiness" ratios) is
centralized here as a validated :mod:`pydantic` model so that a run is fully
described by a single, serializable object. This makes datasets reproducible
and lets configs be checked into version control (as YAML) for repeatable
demos and tests.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class MessinessConfig(BaseModel):
    """Ratios (0.0-1.0) controlling how much "bad data" is injected.

    Each ratio is applied independently and per export target (ERP vs. CRM),
    so the two system exports diverge from each other realistically instead
    of being corrupted identically.
    """

    missing_value_ratio: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Fraction of eligible cells replaced with a missing-value marker.",
    )
    bad_date_ratio: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
        description="Fraction of date cells rewritten in an inconsistent or invalid format.",
    )
    encoding_issue_ratio: float = Field(
        default=0.03,
        ge=0.0,
        le=1.0,
        description="Fraction of text cells corrupted with mixed/mojibake encoding.",
    )
    duplicate_ratio: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
        description="Fraction of rows duplicated (with minor perturbation) per export.",
    )
    orphan_ratio: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Fraction of invoices/payments that exist in only one of the two systems.",
    )
    amount_drift_ratio: float = Field(
        default=0.04,
        ge=0.0,
        le=1.0,
        description="Fraction of payments where the ERP-recorded amount differs slightly from the CRM/true amount.",
    )


class GenerationConfig(BaseModel):
    """Top-level configuration for a single dataset generation run."""

    seed: int = Field(
        default=42, description="Master RNG seed; the same seed always reproduces the same dataset."
    )
    num_customers: int = Field(default=200, gt=0)
    min_invoices_per_customer: int = Field(default=1, ge=0)
    max_invoices_per_customer: int = Field(default=5, ge=0)
    payment_coverage_ratio: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Fraction of invoices that receive at least one payment.",
    )
    output_dir: Path = Field(default=Path("data"))
    with_ground_truth: bool = Field(
        default=False,
        description="Also emit a ground_truth.json mapping for reconciliation validation.",
    )
    messiness: MessinessConfig = Field(default_factory=MessinessConfig)

    @model_validator(mode="after")
    def _check_invoice_range(self) -> GenerationConfig:
        if self.max_invoices_per_customer < self.min_invoices_per_customer:
            raise ValueError("max_invoices_per_customer must be >= min_invoices_per_customer")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> GenerationConfig:
        """Load a config from a YAML file, falling back to defaults for omitted fields."""
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def to_yaml(self, path: Path) -> None:
        """Serialize this config to YAML (useful for recording exactly how a dataset was produced)."""
        path.write_text(
            yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
        )
