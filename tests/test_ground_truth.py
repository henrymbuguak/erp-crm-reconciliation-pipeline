"""Tests for the ground-truth reconciliation mapping."""

from __future__ import annotations

from datagen.config import GenerationConfig
from datagen.generators.invoices import generate_invoices
from datagen.generators.payments import generate_payments
from datagen.ground_truth import build_ground_truth
from datagen.identities import CanonicalCustomer


def test_ground_truth_reflects_orphan_flags(
    customers: list[CanonicalCustomer], small_config: GenerationConfig
) -> None:
    small_config.messiness.orphan_ratio = 0.4
    invoices = generate_invoices(customers, small_config, small_config.seed)
    payments = generate_payments(invoices, small_config, small_config.seed)

    ground_truth = build_ground_truth(invoices, payments)

    invoices_by_id = {str(inv.invoice_id): inv for inv in invoices}
    for entry in ground_truth["invoices"]:
        source = invoices_by_id[entry["invoice_id"]]
        assert entry["expected_match"] == (source.exists_in_erp and source.exists_in_crm)
        assert entry["exists_in_erp"] == source.exists_in_erp
        assert entry["exists_in_crm"] == source.exists_in_crm
        assert (entry["erp_key"] is None) == (not source.exists_in_erp)
        assert (entry["crm_key"] is None) == (not source.exists_in_crm)


def test_ground_truth_summary_counts_match_entries(
    customers: list[CanonicalCustomer], small_config: GenerationConfig
) -> None:
    invoices = generate_invoices(customers, small_config, small_config.seed)
    payments = generate_payments(invoices, small_config, small_config.seed)
    ground_truth = build_ground_truth(invoices, payments)

    assert ground_truth["summary"]["total_invoices"] == len(ground_truth["invoices"])
    assert ground_truth["summary"]["total_payments"] == len(ground_truth["payments"])
    assert ground_truth["summary"]["invoice_orphans"] == sum(
        1 for e in ground_truth["invoices"] if not e["expected_match"]
    )
    assert ground_truth["summary"]["payment_amount_mismatches"] == sum(
        1 for e in ground_truth["payments"] if e["has_amount_mismatch"]
    )
