"""Tests for wiring cleaners into schema-validated records or quarantine entries."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl

from pipeline.models import EntityType, ReasonCode, SourceSystem
from pipeline.validate import validate_customers, validate_invoices, validate_payments


def test_validate_customers_erp_builds_clean_record() -> None:
    df = pl.DataFrame(
        {
            "CUST_ID": ["CUST-000001"],
            "CUST_NAME": ["Alice Smith"],
            "EMAIL_ADDR": ["alice@example.com"],
            "PHONE_NUM": ["555-0100"],
            "ADDR_LINE1": ["1 Main St"],
            "CITY": ["Metropolis"],
            "REGION": ["NY"],
            "POSTAL_CD": ["10001"],
            "COUNTRY": ["USA"],
            "CREATED_DT": ["2024-01-15"],
        }
    )

    clean, quarantined = validate_customers(df, SourceSystem.ERP)

    assert quarantined == []
    assert len(clean) == 1
    record = clean[0]
    assert record.source_system == SourceSystem.ERP
    assert record.business_key == "CUST-000001"
    assert record.full_name == "Alice Smith"
    assert record.created_at == date(2024, 1, 15)


def test_validate_customers_crm_builds_clean_record() -> None:
    df = pl.DataFrame(
        {
            "customerId": ["CUST-000001"],
            "customerName": ["Alice Smith"],
            "email": ["alice@example.com"],
            "phone": ["555-0100"],
            "street": ["1 Main St"],
            "city": ["Metropolis"],
            "region": ["NY"],
            "postalCode": ["10001"],
            "country": ["USA"],
            "createdAt": ["2024-01-15"],
        }
    )

    clean, quarantined = validate_customers(df, SourceSystem.CRM)

    assert quarantined == []
    assert len(clean) == 1
    assert clean[0].source_system == SourceSystem.CRM
    assert clean[0].business_key == "CUST-000001"


def test_validate_customers_quarantines_missing_required_full_name() -> None:
    df = pl.DataFrame(
        {
            "CUST_ID": ["CUST-000001"],
            "CUST_NAME": ["N/A"],  # missing-value marker -> normalized to null
            "EMAIL_ADDR": ["alice@example.com"],
            "PHONE_NUM": ["555-0100"],
            "ADDR_LINE1": ["1 Main St"],
            "CITY": ["Metropolis"],
            "REGION": ["NY"],
            "POSTAL_CD": ["10001"],
            "COUNTRY": ["USA"],
            "CREATED_DT": ["2024-01-15"],
        }
    )

    clean, quarantined = validate_customers(df, SourceSystem.ERP)

    assert clean == []
    assert len(quarantined) == 1
    entry = quarantined[0]
    assert entry.entity_type == EntityType.CUSTOMER
    assert entry.reason_code == ReasonCode.MISSING_REQUIRED_FIELD
    assert entry.stage == "schema_validation"
    # raw value preserved for debugging
    assert entry.original_data["CUST_NAME"] == "N/A"


def test_validate_customers_quarantines_unparseable_created_at() -> None:
    df = pl.DataFrame(
        {
            "CUST_ID": ["CUST-000001"],
            "CUST_NAME": ["Alice Smith"],
            "EMAIL_ADDR": ["alice@example.com"],
            "PHONE_NUM": ["555-0100"],
            "ADDR_LINE1": ["1 Main St"],
            "CITY": ["Metropolis"],
            "REGION": ["NY"],
            "POSTAL_CD": ["10001"],
            "COUNTRY": ["USA"],
            # datagen's invalid-placeholder marker, not a missing marker
            "CREATED_DT": ["TBD"],
        }
    )

    clean, quarantined = validate_customers(df, SourceSystem.ERP)

    assert clean == []
    assert len(quarantined) == 1
    assert quarantined[0].reason_code == ReasonCode.UNPARSEABLE_DATE
    assert quarantined[0].stage == "cleaning"


def test_validate_customers_quarantines_unrecoverable_encoding() -> None:
    df = pl.DataFrame(
        {
            "CUST_ID": ["CUST-000001"],
            "CUST_NAME": ["Already \ufffd corrupted"],
            "EMAIL_ADDR": ["alice@example.com"],
            "PHONE_NUM": ["555-0100"],
            "ADDR_LINE1": ["1 Main St"],
            "CITY": ["Metropolis"],
            "REGION": ["NY"],
            "POSTAL_CD": ["10001"],
            "COUNTRY": ["USA"],
            "CREATED_DT": ["2024-01-15"],
        }
    )

    clean, quarantined = validate_customers(df, SourceSystem.ERP)

    assert clean == []
    assert len(quarantined) == 1
    assert quarantined[0].reason_code == ReasonCode.UNRECOVERABLE_ENCODING
    assert quarantined[0].stage == "cleaning"


def test_validate_invoices_builds_clean_record_with_decimal_amount() -> None:
    df = pl.DataFrame(
        {
            "INV_NO": ["INV-000001"],
            "CUST_ID": ["CUST-000001"],
            "ISSUE_DT": ["2024-01-15"],
            "DUE_DT": ["2024-02-14"],
            "CURR_CD": ["USD"],
            "AMT": ["123.45"],
            "STATUS_CD": ["PAID"],
        }
    )

    clean, quarantined = validate_invoices(df, SourceSystem.ERP)

    assert quarantined == []
    assert len(clean) == 1
    assert clean[0].amount == Decimal("123.45")
    assert clean[0].issue_date == date(2024, 1, 15)


def test_validate_invoices_quarantines_invalid_amount_as_schema_invalid() -> None:
    df = pl.DataFrame(
        {
            "INV_NO": ["INV-000001"],
            "CUST_ID": ["CUST-000001"],
            "ISSUE_DT": ["2024-01-15"],
            "DUE_DT": ["2024-02-14"],
            "CURR_CD": ["USD"],
            "AMT": ["not-a-number"],
            "STATUS_CD": ["PAID"],
        }
    )

    clean, quarantined = validate_invoices(df, SourceSystem.ERP)

    assert clean == []
    assert len(quarantined) == 1
    assert quarantined[0].reason_code == ReasonCode.SCHEMA_INVALID
    assert quarantined[0].stage == "schema_validation"


def test_validate_payments_builds_clean_record() -> None:
    df = pl.DataFrame(
        {
            "PMT_NO": ["PMT-000001"],
            "INV_NO": ["INV-000001"],
            "CUST_ID": ["CUST-000001"],
            "PMT_DT": ["2024-02-01"],
            "AMT": ["100.00"],
            "PMT_METHOD_CD": ["WIRE"],
        }
    )

    clean, quarantined = validate_payments(df, SourceSystem.ERP)

    assert quarantined == []
    assert len(clean) == 1
    assert clean[0].amount == Decimal("100.00")
    assert clean[0].payment_date == date(2024, 2, 1)
