"""Wire the field-level cleaners into schema-validated records or quarantine entries.

For each source-specific raw table, cleans it (see `pipeline.cleaners`) and
validates every row into the matching `Clean*` model from `pipeline.models`,
or a `QuarantineEntry` when it can't be. A row is quarantined for the most
specific reason available: a flagged unparseable date or unrecoverable
encoding failure from the cleaning stage takes priority over a generic
schema-validation failure, since it points at the actual root cause.
"""

from __future__ import annotations

from typing import Any

import polars as pl
from pydantic import BaseModel, ValidationError

from pipeline.cleaners.dates import clean_date_column
from pipeline.cleaners.encoding import clean_encoding_column
from pipeline.cleaners.missing import clean_missing_markers
from pipeline.models import (
    CleanCustomer,
    CleanInvoice,
    CleanPayment,
    EntityType,
    QuarantineEntry,
    ReasonCode,
    SourceSystem,
)

# Column-name maps: canonical field name -> source-specific raw column name.
# Grounded in docs/reference/data-model.md's ERP/CRM field mapping tables.
CUSTOMER_COLUMNS: dict[SourceSystem, dict[str, str]] = {
    SourceSystem.ERP: {
        "business_key": "CUST_ID",
        "full_name": "CUST_NAME",
        "email": "EMAIL_ADDR",
        "phone": "PHONE_NUM",
        "street": "ADDR_LINE1",
        "city": "CITY",
        "region": "REGION",
        "postal_code": "POSTAL_CD",
        "country": "COUNTRY",
        "created_at": "CREATED_DT",
    },
    SourceSystem.CRM: {
        "business_key": "customerId",
        "full_name": "customerName",
        "email": "email",
        "phone": "phone",
        "street": "street",
        "city": "city",
        "region": "region",
        "postal_code": "postalCode",
        "country": "country",
        "created_at": "createdAt",
    },
}

INVOICE_COLUMNS: dict[SourceSystem, dict[str, str]] = {
    SourceSystem.ERP: {
        "business_key": "INV_NO",
        "customer_business_key": "CUST_ID",
        "issue_date": "ISSUE_DT",
        "due_date": "DUE_DT",
        "currency": "CURR_CD",
        "amount": "AMT",
        "status": "STATUS_CD",
    },
    SourceSystem.CRM: {
        "business_key": "invoiceNumber",
        "customer_business_key": "customerId",
        "issue_date": "issueDate",
        "due_date": "dueDate",
        "currency": "currency",
        "amount": "amount",
        "status": "status",
    },
}

PAYMENT_COLUMNS: dict[SourceSystem, dict[str, str]] = {
    SourceSystem.ERP: {
        "business_key": "PMT_NO",
        "invoice_business_key": "INV_NO",
        "payment_date": "PMT_DT",
        "amount": "AMT",
        "method": "PMT_METHOD_CD",
    },
    SourceSystem.CRM: {
        "business_key": "paymentNumber",
        "invoice_business_key": "invoiceNumber",
        "payment_date": "paymentDate",
        "amount": "amount",
        "method": "method",
    },
}

# Only these fields ever go through the corresponding cleaner: datagen only
# corrupts dates on these fields, and only corrupts encoding on customer
# text fields (see src/datagen/exporters/{erp_csv,crm_json}.py).
_CUSTOMER_DATE_FIELDS = ("created_at",)
_CUSTOMER_ENCODING_FIELDS = ("full_name", "street", "city", "region")
_INVOICE_DATE_FIELDS = ("issue_date", "due_date")
_PAYMENT_DATE_FIELDS = ("payment_date",)


def _clean_raw_table(
    df: pl.DataFrame,
    column_map: dict[str, str],
    date_fields: tuple[str, ...],
    encoding_fields: tuple[str, ...],
) -> pl.DataFrame:
    cleaned = clean_missing_markers(df, list(column_map.values()))
    for field in encoding_fields:
        cleaned = clean_encoding_column(cleaned, column_map[field])
    for field in date_fields:
        cleaned = clean_date_column(cleaned, column_map[field])
    return cleaned


def _build_record(
    cleaned_row: dict[str, Any],
    source_system: SourceSystem,
    column_map: dict[str, str],
    model: type[BaseModel],
    date_fields: tuple[str, ...],
    encoding_fields: tuple[str, ...],
) -> tuple[BaseModel, None] | tuple[None, ReasonCode]:
    for field in date_fields:
        if cleaned_row.get(f"{column_map[field]}_invalid"):
            return None, ReasonCode.UNPARSEABLE_DATE
    for field in encoding_fields:
        if cleaned_row.get(f"{column_map[field]}_invalid"):
            return None, ReasonCode.UNRECOVERABLE_ENCODING

    payload: dict[str, Any] = {
        field: value
        for field, raw_column in column_map.items()
        if (value := cleaned_row.get(raw_column)) is not None
    }
    payload["source_system"] = source_system
    try:
        return model(**payload), None
    except ValidationError as exc:
        is_missing = any(error["type"] == "missing" for error in exc.errors())
        reason = ReasonCode.MISSING_REQUIRED_FIELD if is_missing else ReasonCode.SCHEMA_INVALID
        return None, reason


def _validate_table(
    df: pl.DataFrame,
    source_system: SourceSystem,
    entity_type: EntityType,
    column_map: dict[str, str],
    model: type[BaseModel],
    date_fields: tuple[str, ...] = (),
    encoding_fields: tuple[str, ...] = (),
) -> tuple[list[Any], list[QuarantineEntry]]:
    raw_rows = df.to_dicts()
    cleaned_rows = _clean_raw_table(df, column_map, date_fields, encoding_fields).to_dicts()

    clean_records: list[Any] = []
    quarantined: list[QuarantineEntry] = []
    for raw_row, cleaned_row in zip(raw_rows, cleaned_rows, strict=True):
        record, reason = _build_record(
            cleaned_row, source_system, column_map, model, date_fields, encoding_fields
        )
        if record is not None:
            clean_records.append(record)
            continue
        stage = (
            "cleaning"
            if reason in (ReasonCode.UNPARSEABLE_DATE, ReasonCode.UNRECOVERABLE_ENCODING)
            else "schema_validation"
        )
        quarantined.append(
            QuarantineEntry(
                entity_type=entity_type,
                source_system=source_system,
                reason_code=reason,
                stage=stage,
                original_data=raw_row,
            )
        )
    return clean_records, quarantined


def validate_customers(
    df: pl.DataFrame, source_system: SourceSystem
) -> tuple[list[CleanCustomer], list[QuarantineEntry]]:
    return _validate_table(
        df,
        source_system,
        EntityType.CUSTOMER,
        CUSTOMER_COLUMNS[source_system],
        CleanCustomer,
        date_fields=_CUSTOMER_DATE_FIELDS,
        encoding_fields=_CUSTOMER_ENCODING_FIELDS,
    )


def validate_invoices(
    df: pl.DataFrame, source_system: SourceSystem
) -> tuple[list[CleanInvoice], list[QuarantineEntry]]:
    return _validate_table(
        df,
        source_system,
        EntityType.INVOICE,
        INVOICE_COLUMNS[source_system],
        CleanInvoice,
        date_fields=_INVOICE_DATE_FIELDS,
    )


def validate_payments(
    df: pl.DataFrame, source_system: SourceSystem
) -> tuple[list[CleanPayment], list[QuarantineEntry]]:
    return _validate_table(
        df,
        source_system,
        EntityType.PAYMENT,
        PAYMENT_COLUMNS[source_system],
        CleanPayment,
        date_fields=_PAYMENT_DATE_FIELDS,
    )
