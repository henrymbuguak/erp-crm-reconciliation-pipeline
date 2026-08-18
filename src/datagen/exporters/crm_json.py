"""CRM-style nested JSON export (camelCase field names, API-response shape)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pandas as pd

from datagen.config import GenerationConfig
from datagen.identities import CanonicalCustomer, CanonicalInvoice, CanonicalPayment
from datagen.keys import crm_customer_key, crm_invoice_key, crm_payment_key
from datagen.messiness.dates import corrupt_dates
from datagen.messiness.duplicates import add_duplicates
from datagen.messiness.encoding import corrupt_encoding
from datagen.messiness.missing import inject_missing
from datagen.rng import spawn_rngs


def _build_customers_df(customers: list[CanonicalCustomer]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "customerId": crm_customer_key(c.sequence_number),
                "customerName": c.full_name,
                "email": c.email,
                "phone": c.phone,
                "street": c.street,
                "city": c.city,
                "region": c.region,
                "postalCode": c.postal_code,
                "country": c.country,
                "createdAt": c.created_at,
            }
            for c in customers
        ]
    )


def _build_invoices_df(
    invoices: list[CanonicalInvoice], customers_by_id: dict[str, CanonicalCustomer]
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "customerId": crm_customer_key(
                    customers_by_id[str(inv.customer_id)].sequence_number
                ),
                "invoiceNumber": crm_invoice_key(inv.sequence_number),
                "issueDate": inv.issue_date,
                "dueDate": inv.due_date,
                "currency": inv.currency,
                "amount": float(inv.amount),
                "status": inv.status.value,
            }
            for inv in invoices
            if inv.exists_in_crm
        ]
    )


def _build_payments_df(
    payments: list[CanonicalPayment], invoices_by_id: dict[str, CanonicalInvoice]
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "invoiceNumber": crm_invoice_key(
                    invoices_by_id[str(pmt.invoice_id)].sequence_number
                ),
                "paymentNumber": crm_payment_key(pmt.sequence_number),
                "paymentDate": pmt.payment_date,
                "amount": float(pmt.amount),
                "method": pmt.method.value,
            }
            for pmt in payments
            if pmt.exists_in_crm
        ]
    )


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Type-narrowing wrapper: our DataFrames always use plain string column labels."""
    return cast("list[dict[str, Any]]", df.to_dict(orient="records"))


def _nest_payments_into_invoices(
    invoices_df: pd.DataFrame, payments_df: pd.DataFrame
) -> list[dict[str, Any]]:
    payments_by_invoice: dict[str, list[dict[str, Any]]] = {}
    for record in _records(payments_df):
        invoice_number = record.pop("invoiceNumber")
        payments_by_invoice.setdefault(invoice_number, []).append(record)

    invoice_records = []
    for record in _records(invoices_df):
        record["payments"] = payments_by_invoice.get(record["invoiceNumber"], [])
        invoice_records.append(record)
    return invoice_records


def _nest_invoices_into_customers(
    customers_df: pd.DataFrame, invoice_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    invoices_by_customer: dict[str, list[dict[str, Any]]] = {}
    for record in invoice_records:
        customer_id = record.pop("customerId")
        invoices_by_customer.setdefault(customer_id, []).append(record)

    customer_records = []
    for record in _records(customers_df):
        customer_id = record["customerId"]
        address = {
            "street": record.pop("street"),
            "city": record.pop("city"),
            "region": record.pop("region"),
            "postalCode": record.pop("postalCode"),
            "country": record.pop("country"),
        }
        record["address"] = address
        record["invoices"] = invoices_by_customer.get(customer_id, [])
        customer_records.append(record)
    return customer_records


def export_crm_json(
    customers: list[CanonicalCustomer],
    invoices: list[CanonicalInvoice],
    payments: list[CanonicalPayment],
    config: GenerationConfig,
    seed: int,
    output_dir: Path,
) -> None:
    """Write a CRM-style nested customers.json under ``output_dir/crm``."""
    rngs = spawn_rngs(seed, ["customers", "invoices", "payments"])
    messiness = config.messiness

    customers_by_id = {str(c.customer_id): c for c in customers}
    invoices_by_id = {str(i.invoice_id): i for i in invoices}

    customers_df = _build_customers_df(customers)
    customers_df = corrupt_encoding(
        customers_df,
        ["customerName", "street", "city", "region"],
        messiness.encoding_issue_ratio,
        rngs["customers"],
    )
    customers_df = inject_missing(
        customers_df,
        ["phone", "street", "region", "postalCode"],
        messiness.missing_value_ratio,
        rngs["customers"],
    )
    customers_df = corrupt_dates(
        customers_df, ["createdAt"], messiness.bad_date_ratio, rngs["customers"]
    )
    customers_df = add_duplicates(
        customers_df, messiness.duplicate_ratio, rngs["customers"], exclude_columns=("customerId",)
    )
    # Duplicated customerIds must stay unique keys in the nested JSON tree, so
    # re-key any exact-duplicate rows produced by add_duplicates with a suffix.
    customers_df = _dedupe_join_key(customers_df, "customerId")

    invoices_df = _build_invoices_df(invoices, customers_by_id)
    invoices_df = inject_missing(
        invoices_df, ["currency", "status"], messiness.missing_value_ratio, rngs["invoices"]
    )
    invoices_df = corrupt_dates(
        invoices_df, ["issueDate", "dueDate"], messiness.bad_date_ratio, rngs["invoices"]
    )
    invoices_df = add_duplicates(
        invoices_df,
        messiness.duplicate_ratio,
        rngs["invoices"],
        exclude_columns=("invoiceNumber", "customerId"),
    )
    invoices_df = _dedupe_join_key(invoices_df, "invoiceNumber")

    payments_df = _build_payments_df(payments, invoices_by_id)
    payments_df = inject_missing(
        payments_df, ["method"], messiness.missing_value_ratio, rngs["payments"]
    )
    payments_df = corrupt_dates(
        payments_df, ["paymentDate"], messiness.bad_date_ratio, rngs["payments"]
    )
    payments_df = add_duplicates(
        payments_df,
        messiness.duplicate_ratio,
        rngs["payments"],
        exclude_columns=("invoiceNumber", "paymentNumber"),
    )

    invoice_records = _nest_payments_into_invoices(invoices_df, payments_df)
    customer_records = _nest_invoices_into_customers(customers_df, invoice_records)
    customer_records = _replace_nan_with_none(customer_records)

    crm_dir = output_dir / "crm"
    crm_dir.mkdir(parents=True, exist_ok=True)
    (crm_dir / "customers.json").write_text(
        json.dumps(customer_records, indent=2, default=str, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _replace_nan_with_none(value: Any) -> Any:
    """Recursively replace float NaN with ``None`` throughout a nested JSON structure.

    Assigning ``None`` into a pandas column (e.g. via the missing-value
    injector) is silently coerced to float ``NaN`` -- and this survives even
    ``DataFrame.where()``-based cleanup under pandas' newer string dtype.
    Left as float NaN, ``json.dumps`` would emit the non-standard ``NaN``
    literal, which strict JSON parsers reject.
    """
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, dict):
        return {k: _replace_nan_with_none(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_nan_with_none(v) for v in value]
    return value


def _dedupe_join_key(df: pd.DataFrame, key_column: str) -> pd.DataFrame:
    """Suffix repeated join-key values so duplicated rows don't collide when nesting.

    ``add_duplicates`` may copy a row (including its join key) to simulate a
    real duplicate record. That's desirable for flat CSV/tabular consumers,
    but this exporter groups rows into a nested tree keyed by that same
    column, so an exact duplicate key would silently overwrite/merge instead
    of appearing twice. Suffixing preserves the duplicate as a distinct,
    still-messy entry.
    """
    df = df.copy()
    seen: dict[str, int] = {}
    new_keys = []
    for value in df[key_column]:
        seen[value] = seen.get(value, 0) + 1
        new_keys.append(value if seen[value] == 1 else f"{value}-DUP{seen[value]}")
    df[key_column] = new_keys
    return df
