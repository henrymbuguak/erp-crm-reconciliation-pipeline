"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
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


@pytest.fixture
def pg_conn() -> Iterator[psycopg.Connection]:
    """A clean Postgres connection for `pipeline.postgres` integration tests.

    Skipped unless `TEST_DATABASE_URL` is set (see docker-compose.yml for a
    local Postgres to run these against). Drops the pipeline tables up
    front so every test starts from a blank schema, regardless of what a
    previous test left behind.
    """
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL not set; skipping Postgres integration tests")

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DROP TABLE IF EXISTS quarantine_log, crosswalk, payments, invoices, "
                "customers CASCADE"
            )
        yield conn
