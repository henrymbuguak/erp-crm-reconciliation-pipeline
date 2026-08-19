"""Load pipeline results into the Postgres target schema (see `schema.sql`).

This is an additional persistence layer alongside the JSON crosswalk and
quarantine log, not a replacement -- `pipeline.crosswalk` and
`pipeline.quarantine` remain the source of truth that `reconcile run` reads
back on the next invocation. Mirrors their exact idempotency semantics:

- `customers` / `invoices` / `payments` are upserted on `(source_system,
  business_key)` -- each run's clean projection replaces the previous one
  for that key.
- `crosswalk` uses the same reject-on-conflict strategy as
  `pipeline.crosswalk.upsert_crosswalk`: a `canonical_id` is never
  reassigned once `(entity_type, erp_key, crm_key)` already exists.
- `quarantine_log` is replaced in full on every run, matching
  `pipeline.quarantine.write_quarantine_log`'s overwrite (not upsert)
  behavior -- it reflects only the most recent run's failures.

Callers should open the connection as a context manager so a failure
partway through a load rolls back instead of leaving a half-written run:

```python
with psycopg.connect(dsn) as conn:
    load_pipeline_result(conn, result)
```
"""

from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from psycopg import Connection

from pipeline.models import (
    CleanCustomer,
    CleanInvoice,
    CleanPayment,
    CrosswalkEntry,
    QuarantineEntry,
)
from pipeline.orchestrate import PipelineResult

SCHEMA_SQL = resources.files("pipeline").joinpath("schema.sql").read_text(encoding="utf-8")


def create_schema(conn: Connection) -> None:
    """Create all pipeline tables if they don't already exist."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)


def load_customers(conn: Connection, customers: list[CleanCustomer]) -> None:
    with conn.cursor() as cur:
        for customer in customers:
            cur.execute(
                """
                INSERT INTO customers (source_system, business_key, full_name, email, phone,
                    street, city, region, postal_code, country, created_at)
                VALUES (%(source_system)s, %(business_key)s, %(full_name)s, %(email)s,
                    %(phone)s, %(street)s, %(city)s, %(region)s, %(postal_code)s,
                    %(country)s, %(created_at)s)
                ON CONFLICT (source_system, business_key) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    email = EXCLUDED.email,
                    phone = EXCLUDED.phone,
                    street = EXCLUDED.street,
                    city = EXCLUDED.city,
                    region = EXCLUDED.region,
                    postal_code = EXCLUDED.postal_code,
                    country = EXCLUDED.country,
                    created_at = EXCLUDED.created_at
                """,
                customer.model_dump(mode="json"),
            )


def load_invoices(conn: Connection, invoices: list[CleanInvoice]) -> None:
    with conn.cursor() as cur:
        for invoice in invoices:
            cur.execute(
                """
                INSERT INTO invoices (source_system, business_key, customer_business_key,
                    issue_date, due_date, currency, amount, status)
                VALUES (%(source_system)s, %(business_key)s, %(customer_business_key)s,
                    %(issue_date)s, %(due_date)s, %(currency)s, %(amount)s, %(status)s)
                ON CONFLICT (source_system, business_key) DO UPDATE SET
                    customer_business_key = EXCLUDED.customer_business_key,
                    issue_date = EXCLUDED.issue_date,
                    due_date = EXCLUDED.due_date,
                    currency = EXCLUDED.currency,
                    amount = EXCLUDED.amount,
                    status = EXCLUDED.status
                """,
                invoice.model_dump(mode="json"),
            )


def load_payments(conn: Connection, payments: list[CleanPayment]) -> None:
    with conn.cursor() as cur:
        for payment in payments:
            cur.execute(
                """
                INSERT INTO payments (source_system, business_key, invoice_business_key,
                    payment_date, amount, method)
                VALUES (%(source_system)s, %(business_key)s, %(invoice_business_key)s,
                    %(payment_date)s, %(amount)s, %(method)s)
                ON CONFLICT (source_system, business_key) DO UPDATE SET
                    invoice_business_key = EXCLUDED.invoice_business_key,
                    payment_date = EXCLUDED.payment_date,
                    amount = EXCLUDED.amount,
                    method = EXCLUDED.method
                """,
                payment.model_dump(mode="json"),
            )


def load_crosswalk(conn: Connection, entries: list[CrosswalkEntry]) -> None:
    """Upsert `entries`, preserving the existing `canonical_id` on a key collision."""
    with conn.cursor() as cur:
        for entry in entries:
            cur.execute(
                """
                INSERT INTO crosswalk (entity_type, canonical_id, erp_key, crm_key)
                VALUES (%(entity_type)s, %(canonical_id)s, %(erp_key)s, %(crm_key)s)
                ON CONFLICT (entity_type, erp_key, crm_key) DO NOTHING
                """,
                entry.model_dump(mode="json"),
            )


def replace_quarantine(conn: Connection, entries: list[QuarantineEntry]) -> None:
    """Replace the entire `quarantine_log` table with `entries`."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM quarantine_log")
        for entry in entries:
            payload: dict[str, Any] = entry.model_dump(mode="json")
            cur.execute(
                """
                INSERT INTO quarantine_log (entity_type, source_system, reason_code, stage,
                    original_data)
                VALUES (%(entity_type)s, %(source_system)s, %(reason_code)s, %(stage)s,
                    %(original_data)s)
                """,
                payload | {"original_data": _as_jsonb(payload["original_data"])},
            )


def _as_jsonb(value: dict[str, Any]) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def load_pipeline_result(conn: Connection, result: PipelineResult) -> None:
    """Create the schema (if needed) and load a full pipeline run into Postgres.

    Does not commit -- open `conn` as a context manager (`with psycopg.connect(dsn) as
    conn:`) so the whole run commits or rolls back atomically.
    """
    create_schema(conn)
    load_customers(conn, result.erp_customers + result.crm_customers)
    load_invoices(conn, result.erp_invoices + result.crm_invoices)
    load_payments(conn, result.erp_payments + result.crm_payments)
    load_crosswalk(conn, result.crosswalk)
    replace_quarantine(conn, result.quarantine)
