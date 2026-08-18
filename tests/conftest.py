"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from datagen.config import GenerationConfig
from datagen.generators.customers import generate_customers
from datagen.generators.invoices import generate_invoices
from datagen.generators.payments import generate_payments
from datagen.identities import CanonicalCustomer, CanonicalInvoice, CanonicalPayment


@pytest.fixture
def small_config(tmp_path: Path) -> GenerationConfig:
    return GenerationConfig(
        seed=42,
        num_customers=25,
        min_invoices_per_customer=1,
        max_invoices_per_customer=4,
        output_dir=tmp_path / "data",
    )


@pytest.fixture
def customers(small_config: GenerationConfig) -> list[CanonicalCustomer]:
    return generate_customers(small_config.num_customers, small_config.seed)


@pytest.fixture
def invoices(
    customers: list[CanonicalCustomer], small_config: GenerationConfig
) -> list[CanonicalInvoice]:
    return generate_invoices(customers, small_config, small_config.seed)


@pytest.fixture
def payments(
    invoices: list[CanonicalInvoice], small_config: GenerationConfig
) -> list[CanonicalPayment]:
    return generate_payments(invoices, small_config, small_config.seed)
