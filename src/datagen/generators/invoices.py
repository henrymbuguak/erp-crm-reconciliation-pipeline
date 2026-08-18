"""mimesis-based synthetic invoice generation.

Structural cross-system discrepancies (an invoice existing in only one of
ERP/CRM) are decided here since a reconciliation pipeline needs to be able to
detect exactly this kind of divergence.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
from mimesis import Finance
from mimesis.locales import Locale

from datagen.config import GenerationConfig
from datagen.identities import CanonicalCustomer, CanonicalInvoice, InvoiceStatus
from datagen.rng import seeded_uuid4

_STATUS_CHOICES = list(InvoiceStatus)
_STATUS_WEIGHTS = [0.55, 0.15, 0.10, 0.15, 0.05]  # paid, partial, unpaid, overdue, void


def _round_money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generate_invoices(
    customers: list[CanonicalCustomer], config: GenerationConfig, seed: int
) -> list[CanonicalInvoice]:
    """Generate invoices for each customer, per ``config`` volume and messiness settings."""
    finance = Finance(locale=Locale.EN)
    finance.reseed(seed)
    rng = np.random.default_rng(seed)

    invoices: list[CanonicalInvoice] = []
    sequence_number = 1

    for customer in customers:
        num_invoices = int(
            rng.integers(config.min_invoices_per_customer, config.max_invoices_per_customer + 1)
        )
        for _ in range(num_invoices):
            days_ago = int(rng.integers(1, 365 * 2))
            issue_date = date.today() - timedelta(days=days_ago)
            due_date = issue_date + timedelta(days=int(rng.choice([15, 30, 45, 60])))
            amount = _round_money(float(rng.uniform(50.0, 5000.0)))
            currency = finance.currency_iso_code()
            status_idx = rng.choice(len(_STATUS_CHOICES), p=_STATUS_WEIGHTS)
            status = _STATUS_CHOICES[status_idx]

            exists_in_erp = True
            exists_in_crm = True
            if rng.random() < config.messiness.orphan_ratio:
                if rng.random() < 0.5:
                    exists_in_erp = False
                else:
                    exists_in_crm = False

            invoices.append(
                CanonicalInvoice(
                    invoice_id=seeded_uuid4(rng),
                    customer_id=customer.customer_id,
                    sequence_number=sequence_number,
                    issue_date=issue_date,
                    due_date=due_date,
                    currency=str(currency),
                    amount=amount,
                    status=status,
                    exists_in_erp=exists_in_erp,
                    exists_in_crm=exists_in_crm,
                )
            )
            sequence_number += 1

    return invoices
