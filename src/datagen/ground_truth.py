"""Ground-truth reconciliation mapping.

Optionally emitted alongside a generated dataset, this file records the
*actual* cross-system relationships the generator created -- which
invoices/payments exist in both systems, which are orphaned in only one, and
which payments have a legitimate ERP/CRM amount mismatch. A reconciliation
pipeline's output can be scored against this file to measure precision and
recall, since it captures answers that are otherwise undiscoverable purely by
comparing the messy exports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datagen.identities import CanonicalInvoice, CanonicalPayment
from datagen.keys import (
    crm_invoice_key,
    crm_payment_key,
    erp_invoice_key,
    erp_payment_key,
)


def build_ground_truth(
    invoices: list[CanonicalInvoice], payments: list[CanonicalPayment]
) -> dict[str, Any]:
    """Build a JSON-serializable ground-truth reconciliation mapping."""
    invoice_entries = [
        {
            "invoice_id": str(inv.invoice_id),
            "erp_key": erp_invoice_key(inv.sequence_number) if inv.exists_in_erp else None,
            "crm_key": crm_invoice_key(inv.sequence_number) if inv.exists_in_crm else None,
            "exists_in_erp": inv.exists_in_erp,
            "exists_in_crm": inv.exists_in_crm,
            "expected_match": inv.exists_in_erp and inv.exists_in_crm,
        }
        for inv in invoices
    ]

    payment_entries = [
        {
            "payment_id": str(pmt.payment_id),
            "erp_key": erp_payment_key(pmt.sequence_number) if pmt.exists_in_erp else None,
            "crm_key": crm_payment_key(pmt.sequence_number) if pmt.exists_in_crm else None,
            "exists_in_erp": pmt.exists_in_erp,
            "exists_in_crm": pmt.exists_in_crm,
            "expected_match": pmt.exists_in_erp and pmt.exists_in_crm,
            "amount_drift": float(pmt.erp_amount_drift),
            "has_amount_mismatch": pmt.erp_amount_drift != 0,
        }
        for pmt in payments
    ]

    return {
        "invoices": invoice_entries,
        "payments": payment_entries,
        "summary": {
            "total_invoices": len(invoice_entries),
            "invoice_orphans": sum(1 for e in invoice_entries if not e["expected_match"]),
            "total_payments": len(payment_entries),
            "payment_orphans": sum(1 for e in payment_entries if not e["expected_match"]),
            "payment_amount_mismatches": sum(
                1 for e in payment_entries if e["has_amount_mismatch"]
            ),
        },
    }


def write_ground_truth(ground_truth: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(ground_truth, indent=2) + "\n", encoding="utf-8")
