"""Tests for the customer/invoice/payment generators."""

from __future__ import annotations

from datagen.config import GenerationConfig
from datagen.generators.customers import generate_customers
from datagen.generators.invoices import generate_invoices
from datagen.generators.payments import generate_payments
from datagen.identities import CanonicalCustomer, CanonicalInvoice, CanonicalPayment


def test_generate_customers_is_deterministic() -> None:
    first = generate_customers(20, seed=42)
    second = generate_customers(20, seed=42)
    assert [c.model_dump() for c in first] == [c.model_dump() for c in second]


def test_generate_customers_different_seed_differs() -> None:
    first = generate_customers(20, seed=42)
    second = generate_customers(20, seed=99)
    assert first[0].first_name != second[0].first_name or first[0].email != second[0].email


def test_generate_customers_unique_emails_and_sequence(customers: list[CanonicalCustomer]) -> None:
    emails = [c.email for c in customers]
    assert len(emails) == len(set(emails))
    assert [c.sequence_number for c in customers] == list(range(1, len(customers) + 1))


def test_generate_invoices_respects_configured_range(
    customers: list[CanonicalCustomer],
    small_config: GenerationConfig,
    invoices: list[CanonicalInvoice],
) -> None:
    counts: dict[str, int] = {}
    for invoice in invoices:
        counts[str(invoice.customer_id)] = counts.get(str(invoice.customer_id), 0) + 1

    for customer in customers:
        count = counts.get(str(customer.customer_id), 0)
        assert (
            small_config.min_invoices_per_customer
            <= count
            <= small_config.max_invoices_per_customer
        )


def test_generate_invoices_is_deterministic(
    customers: list[CanonicalCustomer], small_config: GenerationConfig
) -> None:
    first = generate_invoices(customers, small_config, small_config.seed)
    second = generate_invoices(customers, small_config, small_config.seed)
    assert [i.model_dump() for i in first] == [i.model_dump() for i in second]


def test_generate_invoices_orphan_ratio_applied_approximately(
    customers: list[CanonicalCustomer],
) -> None:
    config = GenerationConfig(num_customers=len(customers), max_invoices_per_customer=1)
    config.messiness.orphan_ratio = 0.5
    invoices = generate_invoices(customers, config, seed=1)

    orphan_count = sum(1 for inv in invoices if not (inv.exists_in_erp and inv.exists_in_crm))
    orphan_fraction = orphan_count / len(invoices)
    assert 0.3 < orphan_fraction < 0.7


def test_generate_payments_only_for_eligible_statuses(
    invoices: list[CanonicalInvoice], payments: list[CanonicalPayment]
) -> None:
    invoices_by_id = {inv.invoice_id: inv for inv in invoices}
    for payment in payments:
        assert invoices_by_id[payment.invoice_id].status.value in {"paid", "partial", "overdue"}


def test_generate_payments_amount_drift_ratio_applied_approximately(
    invoices: list[CanonicalInvoice],
) -> None:
    config = GenerationConfig(num_customers=1)
    config.messiness.amount_drift_ratio = 0.5
    config.payment_coverage_ratio = 1.0
    payments = generate_payments(invoices, config, seed=2)

    drifted = sum(1 for p in payments if p.erp_amount_drift != 0)
    assert drifted / len(payments) > 0.2


def test_generate_payments_is_deterministic(
    invoices: list[CanonicalInvoice], small_config: GenerationConfig
) -> None:
    first = generate_payments(invoices, small_config, small_config.seed)
    second = generate_payments(invoices, small_config, small_config.seed)
    assert [p.model_dump() for p in first] == [p.model_dump() for p in second]
