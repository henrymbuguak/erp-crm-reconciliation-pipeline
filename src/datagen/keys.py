"""Business-facing key formatting.

ERP and CRM systems virtually never agree on ID formatting even when they
refer to the same underlying entity (one uses zero-padded numeric codes,
another prefixes differently, etc). These helpers derive both systems'
business keys from the same underlying ``sequence_number`` so a
reconciliation pipeline can be built to match them (e.g. by normalizing
digits) instead of relying on the internal correlation UUIDs, which are
never exported.
"""

from __future__ import annotations


def erp_customer_key(sequence_number: int) -> str:
    return f"C{sequence_number:06d}"


def crm_customer_key(sequence_number: int) -> str:
    return f"CUST-{sequence_number:06d}"


def erp_invoice_key(sequence_number: int) -> str:
    return f"INV-{sequence_number:06d}"


def crm_invoice_key(sequence_number: int) -> str:
    return f"INV{sequence_number:06d}"


def erp_payment_key(sequence_number: int) -> str:
    return f"PMT-{sequence_number:06d}"


def crm_payment_key(sequence_number: int) -> str:
    return f"PAY{sequence_number:06d}"
