# CLAUDE.md — Ingestion, Cleaning & Reconciliation Pipeline

This file governs Claude Code for the pipeline phase of this project. The
`datagen` package (data generation) is complete and out of scope for these
rules — treat `src/datagen/**` as read-only reference material, not something
to modify.

## Context Claude Code should know

- Input data lives under a generated `data/` directory (see `examples/sample_dataset`
  for a small committed example): `erp/customers.csv`, `erp/invoices.csv`,
  `erp/payments.csv` (flat CSV, `UPPER_SNAKE_CASE` legacy field names) and
  `crm/customers.json` (nested JSON, `camelCase`, invoices nested under
  customers, payments nested under invoices).
- Field mappings and business-key formats are documented in
  `docs/reference/data-model.md` — read this before writing any parsing code.
- `ground_truth.json` (when present) is an **evaluation artifact only**. It
  records the true ERP/CRM match for every invoice and payment, plus the
  exact amount drift applied. See the rule below — it is never a pipeline
  input.

## Hard constraint: no ID-format shortcuts

The ERP and CRM business keys (`CUST_ID` vs `customerId`, `INV_NO` vs
`invoiceNumber`, etc.) are cosmetically different encodings of the same
underlying sequence number, because this is a synthetic dataset. **Do not
write matching logic that parses, strips, or reverses business-key formats
to align records across systems.** A real legacy migration will not have
this convenient correlation, and code that relies on it isn't doing entity
resolution — it's pattern-matching a lucky detail of the test fixture.

Entity resolution must match records using the same signals a real pipeline
would have: customer name, email, phone, address for customers; and for
invoices, the resolved customer plus date proximity, amount, and currency.
Business keys within a single system may be used as stable identifiers
_within_ that system, just never as a cross-system join key.

Note: `src/datagen/keys.py` documents its divergent business-key formats as
existing so a pipeline "can be built to match them ... by normalizing
digits." This constraint deliberately overrides that suggestion in favor of
realistic entity resolution — call this out explicitly in the pipeline's
own README/docstrings so the two documents don't read as contradicting each
other by accident.

Payments are the one place amount must NOT be a hard match gate: ERP payment
amounts are deliberately drifted from CRM amounts for a subset of records
(`erp_amount_drift`, simulating bank fees/FX rounding), and that drift is
exactly what reconciliation is supposed to catch, not fail on. Match a
payment via its _already-resolved_ invoice plus date proximity first; treat
amount as a tolerance-banded plausibility/flagging signal (e.g. flag when
drift exceeds a configurable threshold) rather than a condition for the
match itself. A tight amount-proximity gate on payments will misclassify
legitimately-drifted, correctly-matching payments as orphans or mismatches.

Use `rapidfuzz` for customer name similarity, combined with normalized
exact email/phone comparison, into one confidence score per candidate pair.

## Resolution outcomes

Every customer/invoice/payment resolves to exactly one of four outcomes —
do not conflate these:

- **Matched** — a candidate pair scores above threshold with no tie: write
  one crosswalk entry with both `erp_key` and `crm_key` populated.
- **Orphan** — zero candidates score above threshold, and nothing about the
  record is malformed: this is not a failure, it's a real one-sided record
  (e.g. a CRM lead with no ERP account yet). Write a crosswalk entry with
  the missing side `null`. Never route this to quarantine.
- **Ambiguous** — two or more candidates tie for the top score: quarantine
  _all_ tied candidates with reason code `ambiguous_match` rather than
  guessing which one is correct.
- **Invalid** — cleaning/validation failed before resolution was even
  attempted (see "Cleaning vs. quarantine" below): quarantine with the
  cleaning-stage reason code.

Getting this distinction wrong distorts the reconciliation report badly —
"40% quarantined" reads as a broken pipeline; "40% orphaned, 2%
quarantined" reads as an accurate picture of two systems that don't fully
overlap, which is the true story a real migration tells. Design
`quarantine.py`'s reason-code enum and `report.py`'s counters around these
four states from the start, before writing schema validation.

### Concrete thresholds, grounded in the generator, not guessed

- **Date proximity.** `src/datagen/generators/payments.py` sets
  `payment_date` to a single value shared by both exports — messiness only
  reformats or corrupts that value, it never shifts it between systems.
  There is no legitimate cross-system date lag to tolerate: match on the
  same calendar date after normalization, not a multi-day window.
- **Amount-drift flag threshold.** `erp_amount_drift` is drawn from
  `uniform(0.01, 5.0)` dollars (absolute, ERP-only) in
  `src/datagen/generators/payments.py` — genuine drift is always ≥ $0.01 in
  magnitude. Flag a payment mismatch when `abs(erp_amount - crm_amount) >
Decimal("0.005")` (a rounding-noise epsilon), not a percentage-based band.
- **Fuzzy-match confidence threshold.** Calibrate offline by sweeping
  values against `eval/score.py` output on a dataset generated with
  `--with-ground-truth`, and pick the value that maximizes F1, then
  hardcode it. This is standard validation-set practice and does not
  violate the `ground_truth.json` eval-only rule below — that rule is
  about runtime consultation, not offline constant-tuning.

## Hard constraint: ground_truth.json is eval-only

`ground_truth.json` must never be imported, read, or referenced by any
module under `src/pipeline/` (or wherever the pipeline package ends up
living). It may only be used in `tests/` or a dedicated `eval/` script that
scores pipeline output for precision/recall after the fact. If a prompt asks
Claude Code to "improve match accuracy," the fix must come from better
matching logic, not from consulting the answer key.

## Cleaning vs. quarantine — do not conflate these

"Cleaning" means repairing recoverable messiness. "Quarantine" means giving
up on a row. Most of the messy data the generator produces is recoverable
and should be _fixed_, not rejected — a pipeline that quarantines every bad
date format isn't a cleaning engine, it's a validation gate. Apply these
per field type:

- **Dates.** Try parsing against every known format the generator can
  produce (`YYYY-MM-DD`, `MM/DD/YYYY`, `DD-MM-YYYY`, Unix timestamp) before
  giving up. Normalize successful parses to UTC ISO-8601. Only quarantine a
  date if it matches none of these, or is a known invalid placeholder like
  `0000-00-00`.
- **Encoding.** Attempt to repair mojibake (UTF-8 bytes misread as CP-1252)
  back to correct UTF-8. Only quarantine if the repaired text still contains
  replacement characters or is otherwise unrecoverable.
- **Missing values.** Define this per field, not globally: fields required
  for reconciliation to function at all (invoice amount, currency, the
  business key itself) → quarantine the row if missing. Fields useful but
  not essential for matching (phone, one of several address lines) → ingest
  with the field left null, so the row still participates in entity
  resolution using whatever signal it does have.
- **Intra-system near-duplicates.** Before validation, detect and collapse
  near-duplicate rows _within a single export_ (same business key, or
  matching content with only whitespace/case differences on non-key
  columns) into one canonical row. This is a separate problem from
  cross-system entity resolution in `resolve.py` — do it here, first, so
  step 3 isn't matching against duplicated noise. Log which rows were
  merged and on what basis.

## Data quality & typing rules

- **Zero silent failures.** Any row that fails schema validation after
  cleaning has been attempted, or resolves to the `invalid` or `ambiguous`
  outcome (see "Resolution outcomes" above), must be written to
  `quarantine_log.json` with the row's original data, a reason code, and
  the pipeline stage where it was caught — never silently dropped. A
  legitimate `orphan` outcome is not a failure and must not be quarantined.
- **PII in logs.** Quarantine entries may retain the fields needed to debug
  the failure, but do not log full email addresses or phone numbers in any
  console/summary output — mask them (e.g. `j***@example.com`) outside of
  the quarantine file itself.
- **IDs.** Mint a fresh UUID v4 for every canonical entity at ingestion time.
  Do not assume access to the internal `customer_id` UUIDs from
  `src/datagen/identities.py` — a real pipeline never sees those; they exist
  only inside the generator.
- **Crosswalk.** Persist a crosswalk table as JSON (e.g.
  `data/processed/crosswalk.json`, pre-Postgres) mapping: new canonical
  UUID ↔ entity type ↔ ERP business key (nullable) ↔ CRM business key
  (nullable). Key each entry on `(entity_type, erp_key, crm_key)`, not just
  the two business keys, so a customer and invoice key can never collide.
  This is required for every matched, orphan, and ambiguous entity — not
  just the matched ones (see "Resolution outcomes" above).
- **Crosswalk known limitation.** Document in `crosswalk.py`'s module
  docstring: keying on `(entity_type, erp_key, crm_key)` means a re-run on
  a corrected export — where a previously-orphaned record now gains its
  missing-side match — reads as a new row and mints a second UUID, rather
  than resolving forward onto the existing one. This is a deliberate,
  stated scope boundary, not a bug to silently work around.
- **Amounts.** Parse all invoice/payment amounts to `Decimal` immediately
  on ingest — never compare formatted strings or floats. The generator
  itself builds amounts via `Decimal(...).quantize(Decimal("0.01"),
ROUND_HALF_UP)` in `src/datagen/generators/invoices.py` /
  `payments.py`; ingestion must preserve that precision.
- **Timestamps.** Normalize all dates/timestamps to UTC ISO-8601 on ingest,
  regardless of source format.
- **Performance.** Use `polars`, not `pandas`, for the ingestion/cleaning
  pipeline itself. (The generator's internal use of `pandas` in
  `src/datagen/messiness/` is unrelated and should not change.) `polars` is
  not yet a project dependency — run `uv add polars` before writing any
  pipeline code that imports it.
- **Schema enforcement.** Define target Pydantic models in
  `src/pipeline/models.py` (or `src/pipeline/schemas/` if it grows) and
  validate every record against them before it's considered clean.

## Idempotency

Re-running the pipeline on the same input files must not duplicate records.
Upsert on the crosswalk's `(entity_type, erp_key, crm_key)` columns, not on
the freshly minted UUID. Document whatever conflict-resolution strategy you
pick (e.g. last-write-wins vs. reject-on-conflict) in the module docstring.
See the crosswalk known limitation above regarding records whose key shape
changes between runs.

## Workflow

- Before editing code, run `uv run pytest` and confirm the existing suite is
  green.
- Every new cleaner, matcher, or validator gets a unit test in `tests/`
  covering at least one edge case it's meant to handle, before moving on.
- Keep `mypy --strict`, `ruff check .`, and `ruff format --check .` passing
  — this repo already enforces all three in CI; don't introduce regressions.
- When a prompt is ambiguous about a business rule (e.g. how to break a tie
  between two candidate matches), stop and ask rather than guessing silently
  — surface the ambiguity in the response instead of picking an arbitrary
  default.

## Reconciliation report

The final report (Markdown, `RECONCILIATION_REPORT.md`) must include, at
minimum:

- Total records ingested per source system.
- Match rate: records resolved to a single canonical entity across both
  systems.
- Quarantine breakdown by reason code.
- Orphan counts (ERP-only, CRM-only) with a sample of flagged records.
- Amount-mismatch count and total drift value, for payments where ERP and
  CRM amounts legitimately disagree.
- When run against a dataset generated `--with-ground-truth`, also report
  precision/recall of the matcher against `ground_truth.json` — computed by
  the separate `eval/` script, not the pipeline itself.
