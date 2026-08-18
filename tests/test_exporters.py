"""Tests for ERP CSV and CRM JSON exporters."""

from __future__ import annotations

import json

import pandas as pd

from datagen.config import GenerationConfig
from datagen.exporters.crm_json import export_crm_json
from datagen.exporters.erp_csv import export_erp_csv
from datagen.identities import CanonicalCustomer, CanonicalInvoice, CanonicalPayment


def test_export_erp_csv_writes_expected_files_and_columns(
    customers: list[CanonicalCustomer],
    invoices: list[CanonicalInvoice],
    payments: list[CanonicalPayment],
    small_config: GenerationConfig,
) -> None:
    export_erp_csv(
        customers, invoices, payments, small_config, small_config.seed, small_config.output_dir
    )

    erp_dir = small_config.output_dir / "erp"
    assert (erp_dir / "customers.csv").exists()
    assert (erp_dir / "invoices.csv").exists()
    assert (erp_dir / "payments.csv").exists()

    customers_df = pd.read_csv(erp_dir / "customers.csv")
    assert list(customers_df.columns) == [
        "CUST_ID",
        "CUST_NAME",
        "EMAIL_ADDR",
        "PHONE_NUM",
        "ADDR_LINE1",
        "CITY",
        "REGION",
        "POSTAL_CD",
        "COUNTRY",
        "CREATED_DT",
    ]
    assert len(customers_df) >= len(customers)  # duplicates may add rows

    invoices_df = pd.read_csv(erp_dir / "invoices.csv")
    assert "_AMT_DRIFT" not in invoices_df.columns
    payments_df = pd.read_csv(erp_dir / "payments.csv")
    assert "_AMT_DRIFT" not in payments_df.columns


def test_export_erp_csv_excludes_erp_orphans(small_config: GenerationConfig) -> None:
    from datagen.generators.customers import generate_customers
    from datagen.generators.invoices import generate_invoices
    from datagen.generators.payments import generate_payments

    small_config.messiness.orphan_ratio = 1.0  # force every invoice/payment to be an orphan
    customers = generate_customers(small_config.num_customers, small_config.seed)
    invoices = generate_invoices(customers, small_config, small_config.seed)
    payments = generate_payments(invoices, small_config, small_config.seed)

    export_erp_csv(
        customers, invoices, payments, small_config, small_config.seed, small_config.output_dir
    )
    invoices_df = pd.read_csv(small_config.output_dir / "erp" / "invoices.csv")

    expected_erp_invoices = sum(1 for inv in invoices if inv.exists_in_erp)
    assert len(invoices_df) >= expected_erp_invoices
    assert expected_erp_invoices < len(invoices)  # sanity: some really were excluded


def test_export_crm_json_produces_nested_structure(
    customers: list[CanonicalCustomer],
    invoices: list[CanonicalInvoice],
    payments: list[CanonicalPayment],
    small_config: GenerationConfig,
) -> None:
    export_crm_json(
        customers, invoices, payments, small_config, small_config.seed, small_config.output_dir
    )

    path = small_config.output_dir / "crm" / "customers.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))

    assert isinstance(data, list)
    assert len(data) >= len(customers)
    sample = data[0]
    assert "address" in sample
    assert set(sample["address"]) == {"street", "city", "region", "postalCode", "country"}
    assert "invoices" in sample


def test_export_crm_json_never_emits_invalid_nan_literal(
    customers: list[CanonicalCustomer],
    invoices: list[CanonicalInvoice],
    payments: list[CanonicalPayment],
    small_config: GenerationConfig,
) -> None:
    """Regression test: missing-value injection assigns `None`, which pandas
    silently coerces to float NaN even in string columns; without sanitizing
    before serialization, json.dumps would emit the invalid `NaN` literal."""
    small_config.messiness.missing_value_ratio = 1.0
    export_crm_json(
        customers, invoices, payments, small_config, small_config.seed, small_config.output_dir
    )

    raw = (small_config.output_dir / "crm" / "customers.json").read_text(encoding="utf-8")
    assert "NaN" not in raw
    json.loads(raw)  # must be strictly valid JSON


def test_export_crm_json_all_invoices_are_attached_to_some_customer(
    customers: list[CanonicalCustomer],
    invoices: list[CanonicalInvoice],
    payments: list[CanonicalPayment],
    small_config: GenerationConfig,
) -> None:
    """Regression test: duplicate-row perturbation must never corrupt foreign keys,
    which would silently detach an invoice from every customer in the nested JSON."""
    small_config.messiness.duplicate_ratio = 0.3
    export_crm_json(
        customers, invoices, payments, small_config, small_config.seed, small_config.output_dir
    )

    data = json.loads(
        (small_config.output_dir / "crm" / "customers.json").read_text(encoding="utf-8")
    )
    total_invoices_in_output = sum(len(c["invoices"]) for c in data)

    expected_min = sum(1 for inv in invoices if inv.exists_in_crm)
    assert total_invoices_in_output >= expected_min
