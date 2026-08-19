"""Integration tests for `pipeline.postgres` -- require a live Postgres.

Skipped automatically when `TEST_DATABASE_URL` is unset (see the `pg_conn`
fixture in `conftest.py`). Run `docker compose up -d postgres` and set
`TEST_DATABASE_URL=postgresql://reconcile:reconcile@localhost:5433/reconcile`
to run these locally; CI runs them against a `services:` Postgres container.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import psycopg

from pipeline.models import (
    CleanCustomer,
    CleanInvoice,
    CleanPayment,
    CrosswalkEntry,
    EntityType,
    QuarantineEntry,
    ReasonCode,
    SourceSystem,
)
from pipeline.postgres import (
    create_schema,
    load_crosswalk,
    load_customers,
    load_invoices,
    load_payments,
    replace_quarantine,
)


def _customer(business_key: str, source_system: SourceSystem = SourceSystem.ERP) -> CleanCustomer:
    return CleanCustomer(
        source_system=source_system,
        business_key=business_key,
        full_name="Ada Lovelace",
        email="ada@example.com",
    )


def _crosswalk_entry(
    erp_key: str | None, crm_key: str | None, entity_type: EntityType = EntityType.CUSTOMER
) -> CrosswalkEntry:
    return CrosswalkEntry(
        entity_type=entity_type, canonical_id=uuid4(), erp_key=erp_key, crm_key=crm_key
    )


def test_create_schema_is_idempotent(pg_conn: psycopg.Connection) -> None:
    create_schema(pg_conn)
    create_schema(pg_conn)  # must not raise on a second run

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        tables = {row[0] for row in cur.fetchall()}

    assert {"customers", "invoices", "payments", "crosswalk", "quarantine_log"} <= tables


def test_load_customers_upserts_on_source_system_and_business_key(
    pg_conn: psycopg.Connection,
) -> None:
    create_schema(pg_conn)
    load_customers(pg_conn, [_customer("C000001")])

    updated = _customer("C000001")
    updated.full_name = "Ada Lovelace-Byron"
    load_customers(pg_conn, [updated])

    with pg_conn.cursor() as cur:
        cur.execute("SELECT full_name FROM customers")
        rows = cur.fetchall()

    assert rows == [("Ada Lovelace-Byron",)]


def test_load_invoices_and_payments(pg_conn: psycopg.Connection) -> None:
    create_schema(pg_conn)

    invoice = CleanInvoice(
        source_system=SourceSystem.ERP,
        business_key="INV-000001",
        customer_business_key="C000001",
        issue_date=date(2026, 1, 1),
        currency="USD",
        amount=Decimal("100.00"),
    )
    payment = CleanPayment(
        source_system=SourceSystem.ERP,
        business_key="PMT-000001",
        invoice_business_key="INV-000001",
        payment_date=date(2026, 1, 15),
        amount=Decimal("100.00"),
    )

    load_invoices(pg_conn, [invoice])
    load_payments(pg_conn, [payment])

    with pg_conn.cursor() as cur:
        cur.execute("SELECT amount FROM invoices WHERE business_key = 'INV-000001'")
        assert cur.fetchone() == (Decimal("100.00"),)
        cur.execute("SELECT amount FROM payments WHERE business_key = 'PMT-000001'")
        assert cur.fetchone() == (Decimal("100.00"),)


def test_load_crosswalk_preserves_canonical_id_on_conflict(pg_conn: psycopg.Connection) -> None:
    create_schema(pg_conn)
    original = _crosswalk_entry("C000001", "CUST-000001")
    load_crosswalk(pg_conn, [original])

    rerun_entry = _crosswalk_entry("C000001", "CUST-000001")
    load_crosswalk(pg_conn, [rerun_entry])

    with pg_conn.cursor() as cur:
        cur.execute("SELECT canonical_id FROM crosswalk")
        rows = cur.fetchall()

    assert rows == [(original.canonical_id,)]


def test_load_crosswalk_nulls_not_distinct_matches_json_tuple_equality(
    pg_conn: psycopg.Connection,
) -> None:
    """Two entries with the same (entity_type, erp_key, None) must count as one, like the
    JSON crosswalk's tuple-keyed upsert -- not two distinct rows, which Postgres's default
    NULL handling in a UNIQUE constraint would otherwise allow."""
    create_schema(pg_conn)
    orphan = _crosswalk_entry("INV-0001", None, entity_type=EntityType.INVOICE)
    load_crosswalk(pg_conn, [orphan])

    same_orphan_again = _crosswalk_entry("INV-0001", None, entity_type=EntityType.INVOICE)
    load_crosswalk(pg_conn, [same_orphan_again])

    with pg_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM crosswalk")
        assert cur.fetchone() == (1,)


def test_replace_quarantine_overwrites_previous_run(pg_conn: psycopg.Connection) -> None:
    create_schema(pg_conn)
    first_run = [
        QuarantineEntry(
            entity_type=EntityType.CUSTOMER,
            source_system=SourceSystem.ERP,
            reason_code=ReasonCode.MISSING_REQUIRED_FIELD,
            stage="validate",
            original_data={"CUST_ID": "C000001"},
        )
    ]
    replace_quarantine(pg_conn, first_run)

    second_run = [
        QuarantineEntry(
            entity_type=EntityType.INVOICE,
            source_system=SourceSystem.CRM,
            reason_code=ReasonCode.SCHEMA_INVALID,
            stage="validate",
            original_data={"invoiceNumber": "INV000002"},
        )
    ]
    replace_quarantine(pg_conn, second_run)

    with pg_conn.cursor() as cur:
        cur.execute("SELECT entity_type, original_data FROM quarantine_log")
        rows = cur.fetchall()

    assert rows == [("invoice", {"invoiceNumber": "INV000002"})]
