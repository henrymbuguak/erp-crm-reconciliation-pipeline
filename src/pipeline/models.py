"""Target clean-entity schemas, quarantine entries, and the crosswalk.

`CleanCustomer` / `CleanInvoice` / `CleanPayment` describe the *post-cleaning*
record shape: one instance per source-system record (an ERP-side and a
CRM-side customer are each validated into this same schema, tagged by
`source_system`), validated before the record is allowed into entity
resolution. A field is required here only if reconciliation cannot function
without it (per CLAUDE.md's "Cleaning vs. quarantine" missing-values rule);
everything else stays optional so a record with a gap still participates in
resolution using whatever signal it does have.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SourceSystem(StrEnum):
    ERP = "erp"
    CRM = "crm"


class EntityType(StrEnum):
    CUSTOMER = "customer"
    INVOICE = "invoice"
    PAYMENT = "payment"


class ReasonCode(StrEnum):
    """Quarantine reason codes, one per failure mode in CLAUDE.md's "Resolution outcomes"."""

    UNPARSEABLE_DATE = "unparseable_date"
    UNRECOVERABLE_ENCODING = "unrecoverable_encoding"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    SCHEMA_INVALID = "schema_invalid"
    AMBIGUOUS_MATCH = "ambiguous_match"


class ResolutionOutcome(StrEnum):
    MATCHED = "matched"
    ORPHAN = "orphan"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class CleanCustomer(BaseModel):
    source_system: SourceSystem
    business_key: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    street: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    created_at: date | None = None


class CleanInvoice(BaseModel):
    source_system: SourceSystem
    business_key: str
    customer_business_key: str
    # issue_date and amount/currency are required: entity resolution matches
    # invoices on resolved customer + date proximity + amount + currency.
    issue_date: date
    due_date: date | None = None
    currency: str
    amount: Decimal
    status: str | None = None


class CleanPayment(BaseModel):
    source_system: SourceSystem
    business_key: str
    invoice_business_key: str
    # payment_date and amount are required: resolution matches a payment via
    # its already-resolved invoice plus date proximity (amount is a
    # tolerance-banded flag, not a match gate -- see CLAUDE.md).
    payment_date: date
    amount: Decimal
    method: str | None = None


class QuarantineEntry(BaseModel):
    entity_type: EntityType
    source_system: SourceSystem
    reason_code: ReasonCode
    stage: str
    original_data: dict[str, Any]


class CrosswalkEntry(BaseModel):
    """One row per matched, orphan, or ambiguous entity -- never just the matched ones."""

    entity_type: EntityType
    canonical_id: UUID
    erp_key: str | None = None
    crm_key: str | None = None


class DuplicateMergeLog(BaseModel):
    """Record of an intra-system near-duplicate cluster collapsed into one canonical row."""

    key_column: str
    key_value: str
    row_count: int
    differing_columns: list[str]
