"""Tests for `pipeline.orchestrate`, run against `examples/sample_dataset`."""

from __future__ import annotations

from pathlib import Path

from pipeline.models import EntityType
from pipeline.orchestrate import run_pipeline

SAMPLE_DATASET = Path(__file__).parent.parent / "examples" / "sample_dataset"


def test_run_pipeline_ingests_and_resolves_sample_dataset() -> None:
    result = run_pipeline(SAMPLE_DATASET)

    assert result.ingest_counts.erp_customers == 8
    assert result.ingest_counts.crm_customers == 8

    customer_entries = [e for e in result.crosswalk if e.entity_type == EntityType.CUSTOMER]
    # Customers always exist in both systems in this generator (no
    # exists_in_erp/exists_in_crm split), so every one should resolve.
    assert len(customer_entries) == 8
    assert all(e.erp_key is not None and e.crm_key is not None for e in customer_entries)


def test_run_pipeline_covers_every_ingested_invoice_and_payment() -> None:
    result = run_pipeline(SAMPLE_DATASET)

    invoice_entries = [e for e in result.crosswalk if e.entity_type == EntityType.INVOICE]
    payment_entries = [e for e in result.crosswalk if e.entity_type == EntityType.PAYMENT]

    erp_invoice_keys = {e.erp_key for e in invoice_entries if e.erp_key is not None}
    crm_invoice_keys = {e.crm_key for e in invoice_entries if e.crm_key is not None}
    assert erp_invoice_keys == {inv.business_key for inv in result.erp_invoices}
    assert crm_invoice_keys == {inv.business_key for inv in result.crm_invoices}

    erp_payment_keys = {e.erp_key for e in payment_entries if e.erp_key is not None}
    crm_payment_keys = {e.crm_key for e in payment_entries if e.crm_key is not None}
    assert erp_payment_keys == {pmt.business_key for pmt in result.erp_payments}
    assert crm_payment_keys == {pmt.business_key for pmt in result.crm_payments}
