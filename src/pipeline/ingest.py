"""Raw ingestion of ERP CSV and CRM nested-JSON exports.

Reads files into polars DataFrames with their *original* column names and
all-`Utf8` dtypes -- no cleaning or type coercion happens here (see
`pipeline.cleaners` for that). Keeping ingestion a pure I/O + flattening step
means messy values (bad date formats, missing-value markers, mojibake)
survive intact for the cleaning stage to handle explicitly, per CLAUDE.md's
"Cleaning vs. quarantine" rule.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple

import polars as pl


class RawTables(NamedTuple):
    erp_customers: pl.DataFrame
    erp_invoices: pl.DataFrame
    erp_payments: pl.DataFrame
    crm_customers: pl.DataFrame
    crm_invoices: pl.DataFrame
    crm_payments: pl.DataFrame


def _read_erp_csv(path: Path) -> pl.DataFrame:
    """Read an ERP CSV with every column as a string; messiness makes dtype inference unsafe."""
    return pl.read_csv(path, infer_schema=False)


def read_erp_tables(erp_dir: Path) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Read `erp/customers.csv`, `erp/invoices.csv`, and `erp/payments.csv`."""
    return (
        _read_erp_csv(erp_dir / "customers.csv"),
        _read_erp_csv(erp_dir / "invoices.csv"),
        _read_erp_csv(erp_dir / "payments.csv"),
    )


def _to_utf8_df(records: list[dict[str, Any]]) -> pl.DataFrame:
    df = pl.DataFrame(records)
    if df.width:
        df = df.with_columns(pl.all().cast(pl.Utf8))
    return df


def _flatten_crm_customers(
    raw_customers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Flatten nested customers -> invoices -> payments into three flat record lists."""
    customer_records: list[dict[str, Any]] = []
    invoice_records: list[dict[str, Any]] = []
    payment_records: list[dict[str, Any]] = []

    for raw_customer in raw_customers:
        customer = dict(raw_customer)
        invoices = customer.pop("invoices", None) or []
        address = customer.pop("address", None) or {}
        customer_id = customer.get("customerId")

        customer_records.append({**customer, **address})

        for raw_invoice in invoices:
            invoice = dict(raw_invoice)
            payments = invoice.pop("payments", None) or []
            invoice_number = invoice.get("invoiceNumber")

            invoice_records.append({**invoice, "customerId": customer_id})

            for payment in payments:
                payment_records.append({**payment, "invoiceNumber": invoice_number})

    return customer_records, invoice_records, payment_records


def read_crm_tables(crm_dir: Path) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Read `crm/customers.json` and flatten it into three flat, all-string DataFrames."""
    raw_customers = json.loads((crm_dir / "customers.json").read_text(encoding="utf-8"))
    customer_records, invoice_records, payment_records = _flatten_crm_customers(raw_customers)
    return (
        _to_utf8_df(customer_records),
        _to_utf8_df(invoice_records),
        _to_utf8_df(payment_records),
    )


def ingest_all(data_dir: Path) -> RawTables:
    """Read both the ERP and CRM exports under `data_dir` into raw, all-string tables."""
    erp_customers, erp_invoices, erp_payments = read_erp_tables(data_dir / "erp")
    crm_customers, crm_invoices, crm_payments = read_crm_tables(data_dir / "crm")
    return RawTables(
        erp_customers=erp_customers,
        erp_invoices=erp_invoices,
        erp_payments=erp_payments,
        crm_customers=crm_customers,
        crm_invoices=crm_invoices,
        crm_payments=crm_payments,
    )
