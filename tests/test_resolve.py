"""Tests for `pipeline.resolve`.

Grounded in two real constraints from CLAUDE.md / the generator:
- Customers have no `exists_in_erp`/`exists_in_crm` split in
  `datagen.identities.CanonicalCustomer` (only invoices/payments do), so a
  customer "orphan" isn't a designed dataset feature -- but the resolver
  must still handle it correctly for a real-world pipeline, so it's tested
  explicitly here with hand-built fixtures.
- Invoice amounts never drift between systems (only payments do, via
  `erp_amount_drift`), so invoice matching is exact-equality; payment
  matching must NOT gate on amount at all, even when it visibly differs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from pipeline.models import (
    CleanCustomer,
    CleanInvoice,
    CleanPayment,
    CrosswalkEntry,
    EntityType,
    ReasonCode,
    SourceSystem,
)
from pipeline.resolve import resolve_customers, resolve_invoices, resolve_payments


def _customer(
    source: SourceSystem, key: str, name: str, email: str | None = None, phone: str | None = None
) -> CleanCustomer:
    return CleanCustomer(
        source_system=source, business_key=key, full_name=name, email=email, phone=phone
    )


def test_resolve_customers_matches_clean_pair_on_name_and_email() -> None:
    erp = [_customer(SourceSystem.ERP, "C000001", "Jane Doe", email="jane.doe@example.com")]
    crm = [_customer(SourceSystem.CRM, "CUST-000001", "Jane Doe", email="jane.doe@example.com")]

    crosswalk, quarantine = resolve_customers(erp, crm)

    assert quarantine == []
    assert len(crosswalk) == 1
    entry = crosswalk[0]
    assert entry.entity_type == EntityType.CUSTOMER
    assert entry.erp_key == "C000001"
    assert entry.crm_key == "CUST-000001"


def test_resolve_customers_matches_despite_dissimilar_business_keys() -> None:
    """No ID-format shortcuts: business keys don't correlate at all here, only name/email do."""
    erp = [_customer(SourceSystem.ERP, "ZZZ-999", "Maria Garcia", email="maria.garcia@example.com")]
    crm = [_customer(SourceSystem.CRM, "AAA-111", "Maria Garcia", email="maria.garcia@example.com")]

    crosswalk, _quarantine = resolve_customers(erp, crm)

    assert len(crosswalk) == 1
    assert crosswalk[0].erp_key == "ZZZ-999"
    assert crosswalk[0].crm_key == "AAA-111"


def test_resolve_customers_orphan_when_no_candidate_clears_threshold() -> None:
    erp = [_customer(SourceSystem.ERP, "C000001", "Jane Doe", email="jane.doe@example.com")]
    crm = [
        _customer(
            SourceSystem.CRM, "CUST-000002", "Totally Different Person", email="other@example.com"
        )
    ]

    crosswalk, quarantine = resolve_customers(erp, crm)

    assert quarantine == []
    assert {(e.erp_key, e.crm_key) for e in crosswalk} == {("C000001", None), (None, "CUST-000002")}


def test_resolve_customers_ambiguous_when_two_candidates_tie() -> None:
    # Name alone (WRatio 1.0 * 0.6 weight = 0.6) doesn't clear the default
    # 0.75 threshold; matching email on both CRM candidates pushes both to
    # an identical, threshold-clearing score so they genuinely tie.
    erp = [_customer(SourceSystem.ERP, "C000001", "John Smith", email="shared@example.com")]
    crm = [
        _customer(SourceSystem.CRM, "CUST-000001", "John Smith", email="shared@example.com"),
        _customer(SourceSystem.CRM, "CUST-000002", "John Smith", email="shared@example.com"),
    ]

    crosswalk, quarantine = resolve_customers(erp, crm)

    assert crosswalk == []
    assert len(quarantine) == 3
    assert all(entry.reason_code == ReasonCode.AMBIGUOUS_MATCH for entry in quarantine)
    assert all(entry.stage == "resolution" for entry in quarantine)
    erp_entries = [e for e in quarantine if e.source_system == SourceSystem.ERP]
    crm_entries = [e for e in quarantine if e.source_system == SourceSystem.CRM]
    assert len(erp_entries) == 1
    assert len(crm_entries) == 2


def _invoice(
    source: SourceSystem, key: str, customer_key: str, amount: str, issue_date: date
) -> CleanInvoice:
    return CleanInvoice(
        source_system=source,
        business_key=key,
        customer_business_key=customer_key,
        issue_date=issue_date,
        currency="USD",
        amount=Decimal(amount),
    )


def _matched_customer_crosswalk(erp_key: str, crm_key: str) -> list[CrosswalkEntry]:
    return [
        CrosswalkEntry(
            entity_type=EntityType.CUSTOMER, canonical_id=uuid4(), erp_key=erp_key, crm_key=crm_key
        )
    ]


def test_resolve_invoices_matches_on_exact_date_currency_amount_within_matched_customer() -> None:
    customer_crosswalk = _matched_customer_crosswalk("C000001", "CUST-000001")
    erp_invoices = [_invoice(SourceSystem.ERP, "INV-0001", "C000001", "100.00", date(2024, 3, 1))]
    crm_invoices = [
        _invoice(SourceSystem.CRM, "IN-0001", "CUST-000001", "100.00", date(2024, 3, 1))
    ]

    crosswalk, quarantine = resolve_invoices(erp_invoices, crm_invoices, customer_crosswalk)

    assert quarantine == []
    assert len(crosswalk) == 1
    assert crosswalk[0].erp_key == "INV-0001"
    assert crosswalk[0].crm_key == "IN-0001"


def test_resolve_invoices_orphan_when_customer_unresolved() -> None:
    erp_invoices = [_invoice(SourceSystem.ERP, "INV-0001", "C000001", "100.00", date(2024, 3, 1))]
    crm_invoices: list[CleanInvoice] = []

    crosswalk, quarantine = resolve_invoices(erp_invoices, crm_invoices, customer_crosswalk=[])

    assert quarantine == []
    assert len(crosswalk) == 1
    assert crosswalk[0].erp_key == "INV-0001"
    assert crosswalk[0].crm_key is None


def test_resolve_invoices_orphan_when_amount_differs() -> None:
    customer_crosswalk = _matched_customer_crosswalk("C000001", "CUST-000001")
    erp_invoices = [_invoice(SourceSystem.ERP, "INV-0001", "C000001", "100.00", date(2024, 3, 1))]
    crm_invoices = [
        _invoice(SourceSystem.CRM, "IN-0001", "CUST-000001", "150.00", date(2024, 3, 1))
    ]

    crosswalk, quarantine = resolve_invoices(erp_invoices, crm_invoices, customer_crosswalk)

    assert quarantine == []
    assert {(e.erp_key, e.crm_key) for e in crosswalk} == {("INV-0001", None), (None, "IN-0001")}


def _payment(
    source: SourceSystem, key: str, invoice_key: str, amount: str, payment_date: date
) -> CleanPayment:
    return CleanPayment(
        source_system=source,
        business_key=key,
        invoice_business_key=invoice_key,
        payment_date=payment_date,
        amount=Decimal(amount),
    )


def _matched_invoice_crosswalk(erp_key: str, crm_key: str) -> list[CrosswalkEntry]:
    return [
        CrosswalkEntry(
            entity_type=EntityType.INVOICE, canonical_id=uuid4(), erp_key=erp_key, crm_key=crm_key
        )
    ]


def test_resolve_payments_matches_on_date_even_when_amount_drifted() -> None:
    """Amount is never a match gate for payments -- erp_amount_drift is expected, not a mismatch."""
    invoice_crosswalk = _matched_invoice_crosswalk("INV-0001", "IN-0001")
    erp_payments = [_payment(SourceSystem.ERP, "PMT-0001", "INV-0001", "101.50", date(2024, 3, 5))]
    crm_payments = [_payment(SourceSystem.CRM, "PY-0001", "IN-0001", "100.00", date(2024, 3, 5))]

    crosswalk, quarantine = resolve_payments(erp_payments, crm_payments, invoice_crosswalk)

    assert quarantine == []
    assert len(crosswalk) == 1
    assert crosswalk[0].erp_key == "PMT-0001"
    assert crosswalk[0].crm_key == "PY-0001"


def test_resolve_payments_orphan_when_date_differs() -> None:
    invoice_crosswalk = _matched_invoice_crosswalk("INV-0001", "IN-0001")
    erp_payments = [_payment(SourceSystem.ERP, "PMT-0001", "INV-0001", "100.00", date(2024, 3, 5))]
    crm_payments = [_payment(SourceSystem.CRM, "PY-0001", "IN-0001", "100.00", date(2024, 3, 6))]

    crosswalk, quarantine = resolve_payments(erp_payments, crm_payments, invoice_crosswalk)

    assert quarantine == []
    assert {(e.erp_key, e.crm_key) for e in crosswalk} == {("PMT-0001", None), (None, "PY-0001")}


def test_resolve_payments_orphan_when_invoice_unresolved() -> None:
    erp_payments = [_payment(SourceSystem.ERP, "PMT-0001", "INV-0001", "100.00", date(2024, 3, 5))]

    crosswalk, quarantine = resolve_payments(erp_payments, [], invoice_crosswalk=[])

    assert quarantine == []
    assert len(crosswalk) == 1
    assert crosswalk[0].erp_key == "PMT-0001"
    assert crosswalk[0].crm_key is None
