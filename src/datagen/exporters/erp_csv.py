"""ERP-style CSV export (legacy flat, upper-snake-case field names)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from datagen.config import GenerationConfig
from datagen.identities import CanonicalCustomer, CanonicalInvoice, CanonicalPayment
from datagen.keys import erp_customer_key, erp_invoice_key, erp_payment_key
from datagen.messiness.dates import corrupt_dates
from datagen.messiness.duplicates import add_duplicates
from datagen.messiness.encoding import corrupt_encoding
from datagen.messiness.mismatches import apply_amount_drift
from datagen.messiness.missing import inject_missing
from datagen.rng import spawn_rngs


def _build_customers_df(customers: list[CanonicalCustomer]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "CUST_ID": erp_customer_key(c.sequence_number),
                "CUST_NAME": c.full_name,
                "EMAIL_ADDR": c.email,
                "PHONE_NUM": c.phone,
                "ADDR_LINE1": c.street,
                "CITY": c.city,
                "REGION": c.region,
                "POSTAL_CD": c.postal_code,
                "COUNTRY": c.country,
                "CREATED_DT": c.created_at,
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
                "INV_NO": erp_invoice_key(inv.sequence_number),
                "CUST_ID": erp_customer_key(customers_by_id[str(inv.customer_id)].sequence_number),
                "ISSUE_DT": inv.issue_date,
                "DUE_DT": inv.due_date,
                "CURR_CD": inv.currency,
                "AMT": float(inv.amount),
                "STATUS_CD": inv.status.value.upper(),
            }
            for inv in invoices
            if inv.exists_in_erp
        ]
    )


def _build_payments_df(
    payments: list[CanonicalPayment],
    customers_by_id: dict[str, CanonicalCustomer],
    invoices_by_id: dict[str, CanonicalInvoice],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PMT_NO": erp_payment_key(pmt.sequence_number),
                "INV_NO": erp_invoice_key(invoices_by_id[str(pmt.invoice_id)].sequence_number),
                "CUST_ID": erp_customer_key(customers_by_id[str(pmt.customer_id)].sequence_number),
                "PMT_DT": pmt.payment_date,
                "AMT": float(pmt.amount),
                "_AMT_DRIFT": float(pmt.erp_amount_drift),
                "PMT_METHOD_CD": pmt.method.value.upper(),
            }
            for pmt in payments
            if pmt.exists_in_erp
        ]
    )


def export_erp_csv(
    customers: list[CanonicalCustomer],
    invoices: list[CanonicalInvoice],
    payments: list[CanonicalPayment],
    config: GenerationConfig,
    seed: int,
    output_dir: Path,
) -> None:
    """Write ERP-style customers/invoices/payments CSVs under ``output_dir/erp``."""
    rngs = spawn_rngs(seed, ["customers", "invoices", "payments"])
    messiness = config.messiness

    customers_by_id = {str(c.customer_id): c for c in customers}
    invoices_by_id = {str(i.invoice_id): i for i in invoices}

    customers_df = _build_customers_df(customers)
    customers_df = corrupt_encoding(
        customers_df,
        ["CUST_NAME", "ADDR_LINE1", "CITY", "REGION"],
        messiness.encoding_issue_ratio,
        rngs["customers"],
    )
    customers_df = inject_missing(
        customers_df,
        ["PHONE_NUM", "ADDR_LINE1", "REGION", "POSTAL_CD"],
        messiness.missing_value_ratio,
        rngs["customers"],
    )
    customers_df = corrupt_dates(
        customers_df, ["CREATED_DT"], messiness.bad_date_ratio, rngs["customers"]
    )
    customers_df = add_duplicates(
        customers_df, messiness.duplicate_ratio, rngs["customers"], exclude_columns=("CUST_ID",)
    )

    invoices_df = _build_invoices_df(invoices, customers_by_id)
    invoices_df = inject_missing(
        invoices_df, ["CURR_CD", "STATUS_CD"], messiness.missing_value_ratio, rngs["invoices"]
    )
    invoices_df = corrupt_dates(
        invoices_df, ["ISSUE_DT", "DUE_DT"], messiness.bad_date_ratio, rngs["invoices"]
    )
    invoices_df = add_duplicates(
        invoices_df,
        messiness.duplicate_ratio,
        rngs["invoices"],
        exclude_columns=("INV_NO", "CUST_ID"),
    )

    payments_df = _build_payments_df(payments, customers_by_id, invoices_by_id)
    payments_df = apply_amount_drift(payments_df, "AMT", "_AMT_DRIFT")
    payments_df = inject_missing(
        payments_df, ["PMT_METHOD_CD"], messiness.missing_value_ratio, rngs["payments"]
    )
    payments_df = corrupt_dates(payments_df, ["PMT_DT"], messiness.bad_date_ratio, rngs["payments"])
    payments_df = add_duplicates(
        payments_df,
        messiness.duplicate_ratio,
        rngs["payments"],
        exclude_columns=("PMT_NO", "INV_NO", "CUST_ID"),
    )

    erp_dir = output_dir / "erp"
    erp_dir.mkdir(parents=True, exist_ok=True)
    customers_df.to_csv(erp_dir / "customers.csv", index=False)
    invoices_df.to_csv(erp_dir / "invoices.csv", index=False)
    payments_df.to_csv(erp_dir / "payments.csv", index=False)
