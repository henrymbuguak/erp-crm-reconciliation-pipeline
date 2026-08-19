"""End-to-end pipeline orchestration: ingest -> dedupe -> validate -> resolve.

Both `eval/score.py` and `pipeline.cli` need to run this exact same sequence
of stages over a data directory, so it's factored out here once rather than
duplicated between them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from pipeline.cleaners.duplicates import collapse_duplicates
from pipeline.ingest import ingest_all
from pipeline.models import (
    CleanCustomer,
    CleanInvoice,
    CleanPayment,
    CrosswalkEntry,
    DuplicateMergeLog,
    QuarantineEntry,
    SourceSystem,
)
from pipeline.report import IngestCounts
from pipeline.resolve import (
    CUSTOMER_MATCH_THRESHOLD,
    resolve_customers,
    resolve_invoices,
    resolve_payments,
)
from pipeline.validate import (
    CUSTOMER_COLUMNS,
    INVOICE_COLUMNS,
    PAYMENT_COLUMNS,
    validate_customers,
    validate_invoices,
    validate_payments,
)


@dataclass
class PipelineResult:
    ingest_counts: IngestCounts
    duplicate_logs: list[DuplicateMergeLog]
    quarantine: list[QuarantineEntry]
    crosswalk: list[CrosswalkEntry]
    erp_customers: list[CleanCustomer] = field(default_factory=list)
    crm_customers: list[CleanCustomer] = field(default_factory=list)
    erp_invoices: list[CleanInvoice] = field(default_factory=list)
    crm_invoices: list[CleanInvoice] = field(default_factory=list)
    erp_payments: list[CleanPayment] = field(default_factory=list)
    crm_payments: list[CleanPayment] = field(default_factory=list)


def run_pipeline(
    data_dir: Path, customer_match_threshold: float = CUSTOMER_MATCH_THRESHOLD
) -> PipelineResult:
    """Run ingestion, intra-system dedup, cleaning/validation, and resolution over `data_dir`.

    `customer_match_threshold` is exposed here (rather than hardcoded) so
    `eval/score.py` can sweep values for offline calibration.
    """
    raw = ingest_all(data_dir)

    ingest_counts = IngestCounts(
        erp_customers=raw.erp_customers.height,
        erp_invoices=raw.erp_invoices.height,
        erp_payments=raw.erp_payments.height,
        crm_customers=raw.crm_customers.height,
        crm_invoices=raw.crm_invoices.height,
        crm_payments=raw.crm_payments.height,
    )

    duplicate_logs: list[DuplicateMergeLog] = []

    def dedupe(df: pl.DataFrame, key_column: str) -> pl.DataFrame:
        deduped, logs = collapse_duplicates(df, key_column)
        duplicate_logs.extend(logs)
        return deduped

    erp_customers_df = dedupe(raw.erp_customers, CUSTOMER_COLUMNS[SourceSystem.ERP]["business_key"])
    crm_customers_df = dedupe(raw.crm_customers, CUSTOMER_COLUMNS[SourceSystem.CRM]["business_key"])
    erp_invoices_df = dedupe(raw.erp_invoices, INVOICE_COLUMNS[SourceSystem.ERP]["business_key"])
    crm_invoices_df = dedupe(raw.crm_invoices, INVOICE_COLUMNS[SourceSystem.CRM]["business_key"])
    erp_payments_df = dedupe(raw.erp_payments, PAYMENT_COLUMNS[SourceSystem.ERP]["business_key"])
    crm_payments_df = dedupe(raw.crm_payments, PAYMENT_COLUMNS[SourceSystem.CRM]["business_key"])

    quarantine: list[QuarantineEntry] = []

    erp_customers, quarantined = validate_customers(erp_customers_df, SourceSystem.ERP)
    quarantine.extend(quarantined)
    crm_customers, quarantined = validate_customers(crm_customers_df, SourceSystem.CRM)
    quarantine.extend(quarantined)
    erp_invoices, quarantined = validate_invoices(erp_invoices_df, SourceSystem.ERP)
    quarantine.extend(quarantined)
    crm_invoices, quarantined = validate_invoices(crm_invoices_df, SourceSystem.CRM)
    quarantine.extend(quarantined)
    erp_payments, quarantined = validate_payments(erp_payments_df, SourceSystem.ERP)
    quarantine.extend(quarantined)
    crm_payments, quarantined = validate_payments(crm_payments_df, SourceSystem.CRM)
    quarantine.extend(quarantined)

    customer_crosswalk, quarantined = resolve_customers(
        erp_customers, crm_customers, threshold=customer_match_threshold
    )
    quarantine.extend(quarantined)
    invoice_crosswalk, quarantined = resolve_invoices(
        erp_invoices, crm_invoices, customer_crosswalk
    )
    quarantine.extend(quarantined)
    payment_crosswalk, quarantined = resolve_payments(erp_payments, crm_payments, invoice_crosswalk)
    quarantine.extend(quarantined)

    return PipelineResult(
        ingest_counts=ingest_counts,
        duplicate_logs=duplicate_logs,
        quarantine=quarantine,
        crosswalk=customer_crosswalk + invoice_crosswalk + payment_crosswalk,
        erp_customers=erp_customers,
        crm_customers=crm_customers,
        erp_invoices=erp_invoices,
        crm_invoices=crm_invoices,
        erp_payments=erp_payments,
        crm_payments=crm_payments,
    )
