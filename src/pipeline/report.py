"""Build the Markdown reconciliation report from pipeline outputs.

Precision/recall against `ground_truth.json` is never computed here -- per
CLAUDE.md's ground_truth.json eval-only rule, only `eval/score.py` (or
tests) may read that file. When available, the caller passes in an
already-computed `PrecisionRecall` to embed in the report; this module
never imports or references `ground_truth.json` itself.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from pipeline.models import CleanPayment, CrosswalkEntry, EntityType, QuarantineEntry, ReasonCode

# Genuine payment drift is always >= $0.01 in magnitude (erp_amount_drift is
# drawn from uniform(0.01, 5.0)); this is a rounding-noise epsilon, not a gate.
AMOUNT_DRIFT_THRESHOLD = Decimal("0.005")


@dataclass
class IngestCounts:
    """Raw row counts per source system, before cleaning/validation."""

    erp_customers: int
    erp_invoices: int
    erp_payments: int
    crm_customers: int
    crm_invoices: int
    crm_payments: int


@dataclass
class PrecisionRecall:
    """Computed by eval/score.py against ground_truth.json -- never by this module."""

    precision: float
    recall: float
    f1: float


@dataclass
class PaymentDrift:
    erp_key: str
    crm_key: str
    erp_amount: Decimal
    crm_amount: Decimal

    @property
    def drift(self) -> Decimal:
        return abs(self.erp_amount - self.crm_amount)


def compute_payment_drift(
    crosswalk: list[CrosswalkEntry],
    erp_payments: list[CleanPayment],
    crm_payments: list[CleanPayment],
) -> list[PaymentDrift]:
    """Flag matched payment pairs whose amounts disagree beyond the rounding epsilon."""
    erp_by_key = {payment.business_key: payment for payment in erp_payments}
    crm_by_key = {payment.business_key: payment for payment in crm_payments}

    drifts: list[PaymentDrift] = []
    for entry in crosswalk:
        if (
            entry.entity_type != EntityType.PAYMENT
            or entry.erp_key is None
            or entry.crm_key is None
        ):
            continue
        erp = erp_by_key.get(entry.erp_key)
        crm = crm_by_key.get(entry.crm_key)
        if erp is None or crm is None:
            continue
        if abs(erp.amount - crm.amount) > AMOUNT_DRIFT_THRESHOLD:
            drifts.append(PaymentDrift(entry.erp_key, entry.crm_key, erp.amount, crm.amount))
    return drifts


def _match_counts(crosswalk: list[CrosswalkEntry], entity_type: EntityType) -> tuple[int, int]:
    entries = [entry for entry in crosswalk if entry.entity_type == entity_type]
    matched = sum(1 for entry in entries if entry.erp_key is not None and entry.crm_key is not None)
    return matched, len(entries)


def _orphans(
    crosswalk: list[CrosswalkEntry], entity_type: EntityType
) -> tuple[list[CrosswalkEntry], list[CrosswalkEntry]]:
    entries = [entry for entry in crosswalk if entry.entity_type == entity_type]
    erp_only = [entry for entry in entries if entry.erp_key is not None and entry.crm_key is None]
    crm_only = [entry for entry in entries if entry.erp_key is None and entry.crm_key is not None]
    return erp_only, crm_only


def _render_ingest_section(counts: IngestCounts) -> str:
    return (
        "## Records ingested per source system\n\n"
        "| Source | Customers | Invoices | Payments |\n"
        "| --- | --- | --- | --- |\n"
        f"| ERP | {counts.erp_customers} | {counts.erp_invoices} | {counts.erp_payments} |\n"
        f"| CRM | {counts.crm_customers} | {counts.crm_invoices} | {counts.crm_payments} |\n"
    )


def _render_match_rate_section(crosswalk: list[CrosswalkEntry]) -> str:
    lines = [
        "## Match rate\n",
        "| Entity | Matched | Total | Match rate |",
        "| --- | --- | --- | --- |",
    ]
    for entity_type in EntityType:
        matched, total = _match_counts(crosswalk, entity_type)
        rate = f"{matched / total:.1%}" if total else "n/a"
        lines.append(f"| {entity_type.value} | {matched} | {total} | {rate} |")
    return "\n".join(lines) + "\n"


def _render_quarantine_section(quarantine: list[QuarantineEntry]) -> str:
    breakdown = Counter(entry.reason_code for entry in quarantine)
    lines = [
        "## Quarantine breakdown\n",
        f"Total quarantined: {len(quarantine)}\n",
        "| Reason code | Count |",
        "| --- | --- |",
    ]
    for reason in ReasonCode:
        lines.append(f"| {reason.value} | {breakdown.get(reason, 0)} |")
    return "\n".join(lines) + "\n"


def _render_sample(entries: list[CrosswalkEntry], sample_size: int) -> str:
    if not entries:
        return "_none_\n"
    lines = [
        f"- `erp_key={entry.erp_key}` `crm_key={entry.crm_key}`" for entry in entries[:sample_size]
    ]
    if len(entries) > sample_size:
        lines.append(f"- ...and {len(entries) - sample_size} more")
    return "\n".join(lines) + "\n"


def _render_orphan_section(crosswalk: list[CrosswalkEntry], sample_size: int) -> str:
    lines = ["## Orphans (records with no counterpart in the other system)\n"]
    for entity_type in EntityType:
        erp_only, crm_only = _orphans(crosswalk, entity_type)
        lines.append(f"### {entity_type.value.capitalize()}\n")
        lines.append(f"ERP-only: {len(erp_only)}\n")
        lines.append(_render_sample(erp_only, sample_size))
        lines.append(f"CRM-only: {len(crm_only)}\n")
        lines.append(_render_sample(crm_only, sample_size))
    return "\n".join(lines)


def _render_drift_section(drifts: list[PaymentDrift]) -> str:
    total_drift = sum((d.drift for d in drifts), start=Decimal("0"))
    lines = [
        "## Payment amount mismatches\n",
        f"Mismatched payments: {len(drifts)}\n",
        f"Total drift: {total_drift}\n",
    ]
    return "\n".join(lines) + "\n"


def _render_precision_recall_section(precision_recall: PrecisionRecall | None) -> str:
    if precision_recall is None:
        return ""
    return (
        "## Precision / recall (against ground truth)\n\n"
        f"- Precision: {precision_recall.precision:.1%}\n"
        f"- Recall: {precision_recall.recall:.1%}\n"
        f"- F1: {precision_recall.f1:.1%}\n"
    )


def render_report(
    ingest_counts: IngestCounts,
    crosswalk: list[CrosswalkEntry],
    quarantine: list[QuarantineEntry],
    erp_payments: list[CleanPayment],
    crm_payments: list[CleanPayment],
    precision_recall: PrecisionRecall | None = None,
    sample_size: int = 5,
) -> str:
    drifts = compute_payment_drift(crosswalk, erp_payments, crm_payments)
    sections = [
        "# Reconciliation Report\n",
        _render_ingest_section(ingest_counts),
        _render_match_rate_section(crosswalk),
        _render_quarantine_section(quarantine),
        _render_orphan_section(crosswalk, sample_size),
        _render_drift_section(drifts),
        _render_precision_recall_section(precision_recall),
    ]
    return "\n".join(section for section in sections if section)


def write_report(content: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
