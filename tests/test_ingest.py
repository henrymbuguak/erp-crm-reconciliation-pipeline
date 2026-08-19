"""Tests for raw ERP/CRM ingestion."""

from __future__ import annotations

from pathlib import Path

from pipeline.ingest import ingest_all

SAMPLE_DATASET = Path(__file__).resolve().parent.parent / "examples" / "sample_dataset"


def test_ingest_all_reads_expected_erp_columns() -> None:
    tables = ingest_all(SAMPLE_DATASET)

    assert tables.erp_customers.columns == [
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
    assert tables.erp_invoices.columns == [
        "INV_NO",
        "CUST_ID",
        "ISSUE_DT",
        "DUE_DT",
        "CURR_CD",
        "AMT",
        "STATUS_CD",
    ]
    assert tables.erp_payments.columns == [
        "PMT_NO",
        "INV_NO",
        "CUST_ID",
        "PMT_DT",
        "AMT",
        "PMT_METHOD_CD",
    ]
    assert tables.erp_customers.height == 8


def test_ingest_all_reads_all_columns_as_strings() -> None:
    tables = ingest_all(SAMPLE_DATASET)

    for table in tables:
        assert all(dtype == table.schema[column] for column, dtype in table.schema.items())
        assert all(str(dtype) == "String" for dtype in table.dtypes)


def test_ingest_all_flattens_crm_customers_invoices_payments() -> None:
    tables = ingest_all(SAMPLE_DATASET)

    assert "customerId" in tables.crm_customers.columns
    assert "street" in tables.crm_customers.columns
    assert "address" not in tables.crm_customers.columns

    assert "customerId" in tables.crm_invoices.columns
    assert "invoiceNumber" in tables.crm_invoices.columns
    assert "payments" not in tables.crm_invoices.columns

    assert "invoiceNumber" in tables.crm_payments.columns
    assert "paymentNumber" in tables.crm_payments.columns

    assert tables.crm_customers.height == tables.erp_customers.height


def test_ingest_all_crm_row_counts_match_nested_json_shape() -> None:
    tables = ingest_all(SAMPLE_DATASET)

    first_customer_invoices = tables.crm_invoices.filter(
        tables.crm_invoices["customerId"] == "CUST-000001"
    )
    assert first_customer_invoices.height == 3

    first_invoice_payments = tables.crm_payments.filter(
        tables.crm_payments["invoiceNumber"] == "INV000001"
    )
    assert first_invoice_payments.height == 1
