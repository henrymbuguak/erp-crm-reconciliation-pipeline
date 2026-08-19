"""Tests for `pipeline.report`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from pipeline.models import (
    CleanPayment,
    CrosswalkEntry,
    DuplicateMergeLog,
    EntityType,
    QuarantineEntry,
    ReasonCode,
    SourceSystem,
)
from pipeline.report import (
    IngestCounts,
    PrecisionRecall,
    compute_payment_drift,
    render_report,
    write_report,
)


def _crosswalk_entry(
    entity_type: EntityType, erp_key: str | None, crm_key: str | None
) -> CrosswalkEntry:
    return CrosswalkEntry(
        entity_type=entity_type, canonical_id=uuid4(), erp_key=erp_key, crm_key=crm_key
    )


def _payment(source: SourceSystem, key: str, amount: str) -> CleanPayment:
    return CleanPayment(
        source_system=source,
        business_key=key,
        invoice_business_key="INV-0001",
        payment_date=date(2024, 3, 5),
        amount=Decimal(amount),
    )


def _ingest_counts() -> IngestCounts:
    return IngestCounts(
        erp_customers=1,
        erp_invoices=1,
        erp_payments=1,
        crm_customers=1,
        crm_invoices=1,
        crm_payments=1,
    )


def test_compute_payment_drift_flags_pair_beyond_rounding_epsilon() -> None:
    crosswalk = [_crosswalk_entry(EntityType.PAYMENT, "PMT-0001", "PY-0001")]
    erp_payments = [_payment(SourceSystem.ERP, "PMT-0001", "101.50")]
    crm_payments = [_payment(SourceSystem.CRM, "PY-0001", "100.00")]

    drifts = compute_payment_drift(crosswalk, erp_payments, crm_payments)

    assert len(drifts) == 1
    assert drifts[0].drift == Decimal("1.50")


def test_compute_payment_drift_ignores_rounding_noise_within_epsilon() -> None:
    crosswalk = [_crosswalk_entry(EntityType.PAYMENT, "PMT-0001", "PY-0001")]
    erp_payments = [_payment(SourceSystem.ERP, "PMT-0001", "100.001")]
    crm_payments = [_payment(SourceSystem.CRM, "PY-0001", "100.00")]

    drifts = compute_payment_drift(crosswalk, erp_payments, crm_payments)

    assert drifts == []


def test_compute_payment_drift_ignores_orphaned_payments() -> None:
    crosswalk = [_crosswalk_entry(EntityType.PAYMENT, "PMT-0001", None)]
    erp_payments = [_payment(SourceSystem.ERP, "PMT-0001", "100.00")]

    drifts = compute_payment_drift(crosswalk, erp_payments, [])

    assert drifts == []


def test_render_report_includes_match_rate_and_quarantine_breakdown() -> None:
    crosswalk = [
        _crosswalk_entry(EntityType.CUSTOMER, "C000001", "CUST-000001"),
        _crosswalk_entry(EntityType.CUSTOMER, "C000002", None),
    ]
    quarantine = [
        QuarantineEntry(
            entity_type=EntityType.CUSTOMER,
            source_system=SourceSystem.ERP,
            reason_code=ReasonCode.AMBIGUOUS_MATCH,
            stage="resolution",
            original_data={},
        )
    ]

    report = render_report(_ingest_counts(), crosswalk, quarantine, [], [])

    assert "customer | 1 | 2 | 50.0%" in report
    assert "ambiguous_match | 1" in report
    assert "ERP-only: 1" in report


def test_render_report_omits_precision_recall_when_not_provided() -> None:
    report = render_report(_ingest_counts(), [], [], [], [])

    assert "Precision" not in report


def test_render_report_executive_summary_reports_success_rate_and_execution_time() -> None:
    quarantine = [
        QuarantineEntry(
            entity_type=EntityType.CUSTOMER,
            source_system=SourceSystem.ERP,
            reason_code=ReasonCode.AMBIGUOUS_MATCH,
            stage="resolution",
            original_data={},
        )
    ]

    report = render_report(_ingest_counts(), [], quarantine, [], [], execution_time_seconds=1.234)

    assert "Total records ingested: 6" in report
    assert "Success rate (ingested, not quarantined): 83.3%" in report
    assert "Records quarantined: 1" in report
    assert "Execution time: 1.23s" in report


def test_render_report_omits_execution_time_when_not_provided() -> None:
    report = render_report(_ingest_counts(), [], [], [], [])

    assert "Execution time" not in report


def test_render_report_includes_duplicates_section() -> None:
    duplicate_logs = [
        DuplicateMergeLog(
            key_column="CUST_ID", key_value="C000001", row_count=2, differing_columns=["CITY"]
        )
    ]

    report = render_report(_ingest_counts(), [], [], [], [], duplicate_logs=duplicate_logs)

    assert "Duplicate groups collapsed: 1" in report
    assert "CUST_ID | C000001 | 2 | CITY" in report


def test_render_report_shows_none_when_no_duplicates_collapsed() -> None:
    report = render_report(_ingest_counts(), [], [], [], [])

    assert "Duplicate groups collapsed: 0" in report


def test_render_report_includes_precision_recall_when_provided() -> None:
    report = render_report(
        _ingest_counts(),
        [],
        [],
        [],
        [],
        precision_recall=PrecisionRecall(precision=0.9, recall=0.8, f1=0.85),
    )

    assert "Precision: 90.0%" in report
    assert "Recall: 80.0%" in report


def test_write_report_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "RECONCILIATION_REPORT.md"

    write_report("# Report\n", path)

    assert path.read_text(encoding="utf-8") == "# Report\n"
