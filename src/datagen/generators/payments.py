"""Synthetic payment generation.

Amount drift between ERP and CRM (representing real-world discrepancies
such as bank fees or FX rounding) is decided here since it requires
knowledge of both systems' views of the same payment.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

import numpy as np

from datagen.config import GenerationConfig
from datagen.identities import CanonicalInvoice, CanonicalPayment, PaymentMethod
from datagen.rng import seeded_uuid4

_METHOD_CHOICES = list(PaymentMethod)
_METHOD_WEIGHTS = [0.45, 0.35, 0.10, 0.10]  # credit_card, bank_transfer, check, cash

# Statuses that imply the invoice has received at least one payment.
_PAID_STATUSES = {"paid", "partial", "overdue"}


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generate_payments(
    invoices: list[CanonicalInvoice], config: GenerationConfig, seed: int
) -> list[CanonicalPayment]:
    """Generate payments against a subset of ``invoices``, per ``config`` settings."""
    rng = np.random.default_rng(seed)

    payments: list[CanonicalPayment] = []
    sequence_number = 1

    for invoice in invoices:
        eligible = invoice.status.value in _PAID_STATUSES
        if not eligible or rng.random() > config.payment_coverage_ratio:
            continue

        is_partial = invoice.status.value == "partial"
        portion = (
            Decimal(str(round(float(rng.uniform(0.3, 0.9)), 2))) if is_partial else Decimal("1")
        )
        amount = _round_money(invoice.amount * portion)

        payment_date = invoice.issue_date + timedelta(days=int(rng.integers(0, 45)))
        method_idx = rng.choice(len(_METHOD_CHOICES), p=_METHOD_WEIGHTS)
        method = _METHOD_CHOICES[method_idx]

        exists_in_erp = invoice.exists_in_erp
        exists_in_crm = invoice.exists_in_crm
        if (
            invoice.exists_in_erp
            and invoice.exists_in_crm
            and rng.random() < config.messiness.orphan_ratio
        ):
            if rng.random() < 0.5:
                exists_in_erp = False
            else:
                exists_in_crm = False

        erp_amount_drift = Decimal("0")
        if rng.random() < config.messiness.amount_drift_ratio:
            drift_magnitude = Decimal(str(round(float(rng.uniform(0.01, 5.0)), 2)))
            erp_amount_drift = drift_magnitude if rng.random() < 0.5 else -drift_magnitude

        payments.append(
            CanonicalPayment(
                payment_id=seeded_uuid4(rng),
                invoice_id=invoice.invoice_id,
                customer_id=invoice.customer_id,
                sequence_number=sequence_number,
                payment_date=payment_date,
                amount=amount,
                method=method,
                exists_in_erp=exists_in_erp,
                exists_in_crm=exists_in_crm,
                erp_amount_drift=erp_amount_drift,
            )
        )
        sequence_number += 1

    return payments
