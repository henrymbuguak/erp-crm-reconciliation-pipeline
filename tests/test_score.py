"""Tests for `eval.score`."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from eval.score import load_ground_truth, score_crosswalk, score_invoices, score_payments
from pipeline.models import CrosswalkEntry, EntityType
from pipeline.orchestrate import run_pipeline

SAMPLE_DATASET = Path(__file__).parent.parent / "examples" / "sample_dataset"


def _entry(entity_type: EntityType, erp_key: str | None, crm_key: str | None) -> CrosswalkEntry:
    return CrosswalkEntry(
        entity_type=entity_type, canonical_id=uuid4(), erp_key=erp_key, crm_key=crm_key
    )


def test_score_invoices_perfect_when_predictions_match_ground_truth() -> None:
    ground_truth = {
        "invoices": [
            {"erp_key": "INV-1", "crm_key": "IN-1", "expected_match": True},
            {"erp_key": "INV-2", "crm_key": None, "expected_match": False},
        ],
        "payments": [],
    }
    crosswalk = [
        _entry(EntityType.INVOICE, "INV-1", "IN-1"),
        _entry(EntityType.INVOICE, "INV-2", None),
    ]

    result = score_invoices(crosswalk, ground_truth)

    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


def test_score_invoices_penalizes_false_positive() -> None:
    ground_truth = {
        "invoices": [{"erp_key": "INV-1", "crm_key": None, "expected_match": False}],
        "payments": [],
    }
    # Pipeline incorrectly claims a match that ground truth says is an orphan.
    crosswalk = [_entry(EntityType.INVOICE, "INV-1", "IN-999")]

    result = score_invoices(crosswalk, ground_truth)

    assert result.precision == 0.0
    assert result.recall == 0.0


def test_score_payments_penalizes_missed_match() -> None:
    ground_truth = {
        "invoices": [],
        "payments": [{"erp_key": "PMT-1", "crm_key": "PY-1", "expected_match": True}],
    }
    # Pipeline failed to find this match at all (both sides orphaned instead).
    crosswalk = [
        _entry(EntityType.PAYMENT, "PMT-1", None),
        _entry(EntityType.PAYMENT, None, "PY-1"),
    ]

    result = score_payments(crosswalk, ground_truth)

    assert result.precision == 0.0
    assert result.recall == 0.0


def test_score_crosswalk_does_not_confuse_invoice_and_payment_keys_that_collide() -> None:
    """Entity-type tagging prevents an invoice key from being scored as a payment match."""
    ground_truth = {
        "invoices": [{"erp_key": "SAME-KEY", "crm_key": "SAME-KEY", "expected_match": True}],
        "payments": [{"erp_key": "SAME-KEY", "crm_key": "SAME-KEY", "expected_match": False}],
    }
    crosswalk = [_entry(EntityType.INVOICE, "SAME-KEY", "SAME-KEY")]

    result = score_crosswalk(crosswalk, ground_truth)

    assert result.precision == 1.0
    assert result.recall == 1.0


def test_load_ground_truth_reads_sample_dataset() -> None:
    ground_truth = load_ground_truth(SAMPLE_DATASET / "ground_truth.json")

    assert "invoices" in ground_truth
    assert "payments" in ground_truth


def test_score_sample_dataset_achieves_reasonable_precision_and_recall() -> None:
    """Integration check: the real matcher against the real generator's ground truth."""
    result = run_pipeline(SAMPLE_DATASET)
    ground_truth = load_ground_truth(SAMPLE_DATASET / "ground_truth.json")

    combined = score_crosswalk(result.crosswalk, ground_truth)

    assert combined.f1 > 0.8
