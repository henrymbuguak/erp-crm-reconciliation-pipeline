"""Canonical ("ground truth") entity models.

These represent the single source of truth for each business entity before
it is projected into system-specific representations (ERP CSV vs. CRM JSON)
and before cosmetic messiness (bad date formats, missing values, encoding
issues) is layered on at export time.

Structural discrepancies that a reconciliation pipeline must detect --
records existing in only one system, or a payment amount that legitimately
differs between systems -- are decided here, since they require knowledge of
*both* systems at once. Cosmetic messiness is applied later, per system, in
`datagen.messiness`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class InvoiceStatus(StrEnum):
    PAID = "paid"
    PARTIAL = "partial"
    UNPAID = "unpaid"
    OVERDUE = "overdue"
    VOID = "void"


class PaymentMethod(StrEnum):
    CREDIT_CARD = "credit_card"
    BANK_TRANSFER = "bank_transfer"
    CHECK = "check"
    CASH = "cash"


class CanonicalCustomer(BaseModel):
    customer_id: UUID
    sequence_number: int
    first_name: str
    last_name: str
    email: str
    phone: str
    street: str
    city: str
    region: str
    postal_code: str
    country: str
    created_at: date

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class CanonicalInvoice(BaseModel):
    invoice_id: UUID
    customer_id: UUID
    sequence_number: int
    issue_date: date
    due_date: date
    currency: str
    amount: Decimal
    status: InvoiceStatus
    exists_in_erp: bool = True
    exists_in_crm: bool = True


class CanonicalPayment(BaseModel):
    payment_id: UUID
    invoice_id: UUID
    customer_id: UUID
    sequence_number: int
    payment_date: date
    amount: Decimal
    method: PaymentMethod
    exists_in_erp: bool = True
    exists_in_crm: bool = True
    # Added to `amount` only in the ERP export, simulating real-world
    # discrepancies such as bank fees or FX rounding that legitimately differ
    # between systems and must be caught by reconciliation logic.
    erp_amount_drift: Decimal = Decimal("0")
