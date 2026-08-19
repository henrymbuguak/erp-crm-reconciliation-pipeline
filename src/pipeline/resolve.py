"""Entity resolution: match ERP and CRM records into a canonical crosswalk.

Per CLAUDE.md's hard constraint, matching never relies on business-key
format shortcuts (`CUST_ID` vs `customerId` are cosmetically different
encodings of the same sequence number only because this is a synthetic
dataset -- a real migration would not have that convenient correlation).
Instead:

- **Customers** are matched on `full_name` similarity (`rapidfuzz`) combined
  with normalized exact email/phone comparison into one confidence score
  per candidate pair. `datagen.identities.CanonicalCustomer` has no
  `exists_in_erp`/`exists_in_crm` split (unlike invoices/payments), so a
  genuine customer orphan is not a designed feature of the generator -- but
  it is still handled correctly here rather than assumed away, since a real
  pipeline can't rely on that.
- **Invoices** are matched within an *already-resolved* customer's own
  invoices only, on exact (`issue_date`, `currency`, `amount`) equality.
  There is no legitimate cross-system date lag or amount drift for
  invoices (only payments drift), so this is an exact join, not a fuzzy
  score, scoped to the matched customer pair.
- **Payments** are matched within an already-resolved invoice's own
  payments, on exact `payment_date` equality *only*. Amount is
  deliberately drifted for some ERP payments (`erp_amount_drift`) to
  simulate bank fees/FX rounding, so amount is never part of the match
  gate here -- flagging that drift is report.py's job, using the crosswalk
  this module produces to look the matched pair's amounts back up.

Every entity resolves to exactly one of four `ResolutionOutcome`s (see
CLAUDE.md's "Resolution outcomes"), decided per-record via mutual top-match
agreement to avoid many-to-one collisions:

- **Matched** -- a record's unique top-scoring candidate (score >=
  threshold) also has *it* as its own unique top-scoring candidate: one
  `CrosswalkEntry` with both keys populated.
- **Orphan** -- zero candidates score >= threshold: a `CrosswalkEntry` with
  the missing side `null`. Never quarantined.
- **Ambiguous** -- the record has a candidate >= threshold but the mutual
  top-match agreement above doesn't hold (multiple tied top candidates on
  either side, or a non-reciprocal top pick): every record on both sides of
  that tie is quarantined with `ReasonCode.AMBIGUOUS_MATCH`, rather than
  guessing which one is correct.
- **Invalid** -- handled upstream by `validate.py`; this module never sees
  those records.

The customer fuzzy-match confidence threshold below was calibrated per
CLAUDE.md by sweeping `eval/score.py data/raw --threshold <value>` (500
customers, `--with-ground-truth`) from 0.1 to 1.0 in increments of 0.05:
combined invoice+payment F1 is flat at its maximum (86.6%) across the
entire 0.1-0.95 range and only drops (to 85.4%) at 0.99-1.0, where an
exact-match-only gate starts rejecting genuine matches with a merely
near-identical name. 0.75 sits well inside that plateau, away from that
edge.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from rapidfuzz import fuzz

from pipeline.models import (
    CleanCustomer,
    CleanInvoice,
    CleanPayment,
    CrosswalkEntry,
    EntityType,
    QuarantineEntry,
    ReasonCode,
    SourceSystem,
)

# Weights for combining name similarity + exact email/phone match into one
# customer confidence score (0..1). Name carries most of the weight and is
# by itself almost always sufficient: datagen never corrupts a name beyond
# recoverable mojibake (an unrecoverable one is quarantined long before
# reaching resolve.py), so the true match's cleaned full_name is normally
# byte-identical across systems. Email/phone are smaller corroborating
# signals for the rarer case of a genuinely imperfect name match.
_NAME_WEIGHT = 0.8
_EMAIL_WEIGHT = 0.15
_PHONE_WEIGHT = 0.05

# Calibrated against eval/score.py -- see module docstring for the sweep.
CUSTOMER_MATCH_THRESHOLD = 0.75


@dataclass
class PairResolution[A, B]:
    """Result of resolving one side's records (`A`) against the other (`B`)."""

    matched: list[tuple[A, B]]
    orphans_a: list[A]
    orphans_b: list[B]
    ambiguous_a: list[tuple[A, list[B]]]
    ambiguous_b: list[tuple[B, list[A]]]


def _resolve_pairs[A, B](
    items_a: Sequence[A],
    items_b: Sequence[B],
    score: Callable[[A, B], float],
    threshold: float,
) -> PairResolution[A, B]:
    """Resolve `items_a` against `items_b` via mutual top-match agreement.

    For each record, candidates are the other side's records scoring >=
    `threshold`, and its "top candidates" are whichever of those share the
    single highest score. A pair is matched only if each is the other's
    unique top candidate (mutual agreement) -- this avoids two records on
    one side both claiming the same record on the other side. Anything
    left over is either an orphan (no candidate cleared the threshold at
    all) or ambiguous (a candidate cleared the threshold but mutual
    agreement didn't hold).
    """
    scores = [[score(a, b) for b in items_b] for a in items_a]

    def top_candidates(row: list[float]) -> tuple[float | None, list[int]]:
        above = [(idx, s) for idx, s in enumerate(row) if s >= threshold]
        if not above:
            return None, []
        top = max(s for _, s in above)
        return top, [idx for idx, s in above if s == top]

    a_top = [top_candidates(row) for row in scores]
    b_top = [
        top_candidates([scores[i][j] for i in range(len(items_a))]) for j in range(len(items_b))
    ]

    matched: list[tuple[A, B]] = []
    matched_a: set[int] = set()
    matched_b: set[int] = set()

    for i, (top_score, candidates) in enumerate(a_top):
        if top_score is None or len(candidates) != 1:
            continue
        j = candidates[0]
        b_top_score, b_candidates = b_top[j]
        if b_top_score is not None and len(b_candidates) == 1 and b_candidates[0] == i:
            matched.append((items_a[i], items_b[j]))
            matched_a.add(i)
            matched_b.add(j)

    orphans_a: list[A] = []
    ambiguous_a: list[tuple[A, list[B]]] = []
    for i, (top_score, candidates) in enumerate(a_top):
        if i in matched_a:
            continue
        if top_score is None:
            orphans_a.append(items_a[i])
        else:
            ambiguous_a.append((items_a[i], [items_b[j] for j in candidates]))

    orphans_b: list[B] = []
    ambiguous_b: list[tuple[B, list[A]]] = []
    for j, (top_score, candidates) in enumerate(b_top):
        if j in matched_b:
            continue
        if top_score is None:
            orphans_b.append(items_b[j])
        else:
            ambiguous_b.append((items_b[j], [items_a[i] for i in candidates]))

    return PairResolution(matched, orphans_a, orphans_b, ambiguous_a, ambiguous_b)


def _crosswalk_entry(
    entity_type: EntityType, erp_key: str | None, crm_key: str | None
) -> CrosswalkEntry:
    return CrosswalkEntry(
        entity_type=entity_type, canonical_id=uuid4(), erp_key=erp_key, crm_key=crm_key
    )


def _ambiguous_entry(
    entity_type: EntityType, source_system: SourceSystem, original_data: dict[str, Any]
) -> QuarantineEntry:
    return QuarantineEntry(
        entity_type=entity_type,
        source_system=source_system,
        reason_code=ReasonCode.AMBIGUOUS_MATCH,
        stage="resolution",
        original_data=original_data,
    )


def _pairs_to_crosswalk_and_quarantine(
    result: PairResolution[Any, Any],
    entity_type: EntityType,
    key_of: Callable[[Any], str],
) -> tuple[list[CrosswalkEntry], list[QuarantineEntry]]:
    crosswalk: list[CrosswalkEntry] = []
    quarantine: list[QuarantineEntry] = []

    for erp, crm in result.matched:
        crosswalk.append(_crosswalk_entry(entity_type, key_of(erp), key_of(crm)))
    for erp in result.orphans_a:
        crosswalk.append(_crosswalk_entry(entity_type, key_of(erp), None))
    for crm in result.orphans_b:
        crosswalk.append(_crosswalk_entry(entity_type, None, key_of(crm)))
    for erp, _candidates in result.ambiguous_a:
        quarantine.append(
            _ambiguous_entry(entity_type, SourceSystem.ERP, erp.model_dump(mode="json"))
        )
    for crm, _candidates in result.ambiguous_b:
        quarantine.append(
            _ambiguous_entry(entity_type, SourceSystem.CRM, crm.model_dump(mode="json"))
        )

    return crosswalk, quarantine


def _normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits or None


def _customer_confidence(erp: CleanCustomer, crm: CleanCustomer) -> float:
    name_score = fuzz.WRatio(erp.full_name, crm.full_name) / 100.0

    erp_email, crm_email = _normalize_email(erp.email), _normalize_email(crm.email)
    email_match = erp_email is not None and erp_email == crm_email

    erp_phone, crm_phone = _normalize_phone(erp.phone), _normalize_phone(crm.phone)
    phone_match = erp_phone is not None and erp_phone == crm_phone

    return (
        _NAME_WEIGHT * name_score
        + _EMAIL_WEIGHT * float(email_match)
        + _PHONE_WEIGHT * float(phone_match)
    )


def resolve_customers(
    erp_customers: Sequence[CleanCustomer],
    crm_customers: Sequence[CleanCustomer],
    threshold: float = CUSTOMER_MATCH_THRESHOLD,
) -> tuple[list[CrosswalkEntry], list[QuarantineEntry]]:
    """Match ERP/CRM customers on name + email/phone confidence.

    Returns `(crosswalk_entries, quarantine_entries)` covering every input
    customer exactly once (matched, orphan, or ambiguous -- never dropped).
    """
    result = _resolve_pairs(erp_customers, crm_customers, _customer_confidence, threshold)
    return _pairs_to_crosswalk_and_quarantine(result, EntityType.CUSTOMER, lambda c: c.business_key)


def _invoice_exact_match(erp: CleanInvoice, crm: CleanInvoice) -> float:
    same = (
        erp.issue_date == crm.issue_date
        and erp.currency == crm.currency
        and erp.amount == crm.amount
    )
    return 1.0 if same else 0.0


def resolve_invoices(
    erp_invoices: Sequence[CleanInvoice],
    crm_invoices: Sequence[CleanInvoice],
    customer_crosswalk: Sequence[CrosswalkEntry],
) -> tuple[list[CrosswalkEntry], list[QuarantineEntry]]:
    """Match ERP/CRM invoices, scoped to each already-resolved customer pair.

    An invoice whose customer wasn't matched (orphan or ambiguous on the
    customer side) has no counterpart to compare against, so it resolves
    straight to orphan -- there's nothing to be ambiguous *about* without a
    resolved parent.
    """
    matched_customers = {
        entry.erp_key: entry.crm_key
        for entry in customer_crosswalk
        if entry.entity_type == EntityType.CUSTOMER
        and entry.erp_key is not None
        and entry.crm_key is not None
    }

    erp_by_customer: dict[str, list[CleanInvoice]] = defaultdict(list)
    for invoice in erp_invoices:
        erp_by_customer[invoice.customer_business_key].append(invoice)

    crm_by_customer: dict[str, list[CleanInvoice]] = defaultdict(list)
    for invoice in crm_invoices:
        crm_by_customer[invoice.customer_business_key].append(invoice)

    crosswalk: list[CrosswalkEntry] = []
    quarantine: list[QuarantineEntry] = []

    for erp_customer_key, group_erp in erp_by_customer.items():
        crm_customer_key = matched_customers.get(erp_customer_key)
        if crm_customer_key is None:
            for invoice in group_erp:
                crosswalk.append(_crosswalk_entry(EntityType.INVOICE, invoice.business_key, None))
            continue

        group_crm = crm_by_customer.pop(crm_customer_key, [])
        result = _resolve_pairs(group_erp, group_crm, _invoice_exact_match, threshold=1.0)
        group_crosswalk, group_quarantine = _pairs_to_crosswalk_and_quarantine(
            result, EntityType.INVOICE, lambda inv: inv.business_key
        )
        crosswalk.extend(group_crosswalk)
        quarantine.extend(group_quarantine)

    # CRM invoices left over: either their customer was never matched at all,
    # or it was matched but happens to have zero ERP invoices.
    for group_crm in crm_by_customer.values():
        for invoice in group_crm:
            crosswalk.append(_crosswalk_entry(EntityType.INVOICE, None, invoice.business_key))

    return crosswalk, quarantine


def _payment_exact_match(erp: CleanPayment, crm: CleanPayment) -> float:
    return 1.0 if erp.payment_date == crm.payment_date else 0.0


def resolve_payments(
    erp_payments: Sequence[CleanPayment],
    crm_payments: Sequence[CleanPayment],
    invoice_crosswalk: Sequence[CrosswalkEntry],
) -> tuple[list[CrosswalkEntry], list[QuarantineEntry]]:
    """Match ERP/CRM payments, scoped to each already-resolved invoice pair.

    Matches on `payment_date` equality only -- amount is deliberately
    drifted for some ERP payments and is never a match gate here (see
    module docstring); report.py flags drift by looking the matched pair's
    amounts back up via the crosswalk this returns.
    """
    matched_invoices = {
        entry.erp_key: entry.crm_key
        for entry in invoice_crosswalk
        if entry.entity_type == EntityType.INVOICE
        and entry.erp_key is not None
        and entry.crm_key is not None
    }

    erp_by_invoice: dict[str, list[CleanPayment]] = defaultdict(list)
    for payment in erp_payments:
        erp_by_invoice[payment.invoice_business_key].append(payment)

    crm_by_invoice: dict[str, list[CleanPayment]] = defaultdict(list)
    for payment in crm_payments:
        crm_by_invoice[payment.invoice_business_key].append(payment)

    crosswalk: list[CrosswalkEntry] = []
    quarantine: list[QuarantineEntry] = []

    for erp_invoice_key, group_erp in erp_by_invoice.items():
        crm_invoice_key = matched_invoices.get(erp_invoice_key)
        if crm_invoice_key is None:
            for payment in group_erp:
                crosswalk.append(_crosswalk_entry(EntityType.PAYMENT, payment.business_key, None))
            continue

        group_crm = crm_by_invoice.pop(crm_invoice_key, [])
        result = _resolve_pairs(group_erp, group_crm, _payment_exact_match, threshold=1.0)
        group_crosswalk, group_quarantine = _pairs_to_crosswalk_and_quarantine(
            result, EntityType.PAYMENT, lambda pmt: pmt.business_key
        )
        crosswalk.extend(group_crosswalk)
        quarantine.extend(group_quarantine)

    for group_crm in crm_by_invoice.values():
        for payment in group_crm:
            crosswalk.append(_crosswalk_entry(EntityType.PAYMENT, None, payment.business_key))

    return crosswalk, quarantine
