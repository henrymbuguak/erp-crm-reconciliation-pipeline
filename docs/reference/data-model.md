# Data model reference

## Canonical entities

The ERP and CRM exports are both projections of the same internal
[canonical entities](api.md#datagen.identities): `CanonicalCustomer`,
`CanonicalInvoice`, and `CanonicalPayment`. See
[`src/datagen/identities.py`](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/blob/main/src/datagen/identities.py)
for the full field list.

## ERP and CRM field mapping

### Customers

| Canonical field               | ERP CSV column                   | CRM JSON field                          |
| ----------------------------- | -------------------------------- | --------------------------------------- |
| `customer_id` (internal only) | --                               | --                                      |
| business key                  | `CUST_ID`, for example `C000001` | `customerId`, for example `CUST-000001` |
| `full_name`                   | `CUST_NAME`                      | `customerName`                          |
| `email`                       | `EMAIL_ADDR`                     | `email`                                 |
| `phone`                       | `PHONE_NUM`                      | `phone`                                 |
| `street`                      | `ADDR_LINE1`                     | `address.street`                        |
| `city`                        | `CITY`                           | `address.city`                          |
| `region`                      | `REGION`                         | `address.region`                        |
| `postal_code`                 | `POSTAL_CD`                      | `address.postalCode`                    |
| `country`                     | `COUNTRY`                        | `address.country`                       |
| `created_at`                  | `CREATED_DT`                     | `createdAt`                             |

### Invoices

| Canonical field                   | ERP CSV column                     | CRM JSON field                                                             |
| --------------------------------- | ---------------------------------- | -------------------------------------------------------------------------- |
| business key                      | `INV_NO`, for example `INV-000001` | `invoiceNumber`, for example `INV000001`, nested under the owning customer |
| `issue_date`                      | `ISSUE_DT`                         | `issueDate`                                                                |
| `due_date`                        | `DUE_DT`                           | `dueDate`                                                                  |
| `currency`                        | `CURR_CD`                          | `currency`                                                                 |
| `amount`                          | `AMT`                              | `amount`                                                                   |
| `status`                          | `STATUS_CD` (upper-cased)          | `status`                                                                   |
| `exists_in_erp` / `exists_in_crm` | row omitted if `False`             | entry omitted if `False`                                                   |

### Payments

| Canonical field | ERP CSV column                      | CRM JSON field                                                            |
| --------------- | ----------------------------------- | ------------------------------------------------------------------------- |
| business key    | `PMT_NO`, for example `PMT-000001`  | `paymentNumber`, for example `PAY000001`, nested under the owning invoice |
| `payment_date`  | `PMT_DT`                            | `paymentDate`                                                             |
| `amount`        | `AMT` (`amount + erp_amount_drift`) | `amount` (canonical amount, undrifted)                                    |
| `method`        | `PMT_METHOD_CD` (upper-cased)       | `method`                                                                  |

`erp_amount_drift` exists specifically so the ERP-recorded amount can
legitimately differ from the CRM/true amount -- simulating bank fees or FX
rounding that a real reconciliation pipeline must detect rather than
silently average away.

## Messiness knobs

Each ratio (0.0-1.0) applies independently, per export, with
independently seeded RNG streams (see
[`datagen.rng.spawn_rngs`](api.md#datagen.rng)) -- so the ERP and CRM copies
of the same underlying row diverge realistically instead of matching each
other's corruption exactly.

| Knob                   | Module                                                         | Effect                                                                                                      |
| ---------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `missing_value_ratio`  | `datagen.messiness.missing`                                    | Replaces cells with `None`, `""`, `"N/A"`, `"NULL"`, `"--"`, or `"unknown"`                                 |
| `bad_date_ratio`       | `datagen.messiness.dates`                                      | Rewrites dates as `MM/DD/YYYY`, `DD-MM-YYYY`, a Unix timestamp, or an invalid placeholder like `0000-00-00` |
| `encoding_issue_ratio` | `datagen.messiness.encoding`                                   | Corrupts text with mojibake (UTF-8 bytes misread as CP-1252)                                                |
| `duplicate_ratio`      | `datagen.messiness.duplicates`                                 | Appends near-duplicate rows (whitespace/case perturbed on a non-key column)                                 |
| `orphan_ratio`         | `datagen.generators.invoices` / `payments`                     | Decides which invoices/payments exist in only one system                                                    |
| `amount_drift_ratio`   | `datagen.generators.payments` + `datagen.messiness.mismatches` | Decides which payments get a legitimate ERP/CRM amount mismatch                                             |

## Ground truth mapping

With `--with-ground-truth`, `ground_truth.json` records, for every invoice
and payment: whether it exists in ERP, CRM, or both (`expected_match`), its
business key in each system (or `null` if absent), and -- for payments --
the exact `amount_drift` applied. A `summary` block totals orphan and
amount-mismatch counts. This is the answer key: you can score a downstream reconciliation
pipeline's output against it for precision and recall.

## Pipeline data model

The reconciliation pipeline (`src/pipeline/`) re-validates every ERP and
CRM row into its own [target schemas](api.md#pipeline.models) before
matching:

| Model                                             | Purpose                                                                                                                                                                  |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `CleanCustomer` / `CleanInvoice` / `CleanPayment` | Post-cleaning record shape, one instance per source-system row, tagged with `source_system`                                                                              |
| `QuarantineEntry`                                 | `entity_type`, `source_system`, `reason_code`, `stage`, and the row's original data -- written for every row that fails cleaning/validation or ties on entity resolution |
| `CrosswalkEntry`                                  | `entity_type`, a freshly minted `canonical_id` (UUID v4), and the nullable `erp_key` / `crm_key` -- one row per matched, orphan, _or_ ambiguous entity                   |
| `ReasonCode`                                      | `unparseable_date`, `unrecoverable_encoding`, `missing_required_field`, `schema_invalid`, `ambiguous_match`                                                              |

### Entity resolution never uses ID-format shortcuts

`CUST_ID` (ERP) and `customerId` (CRM) are cosmetically different encodings
of the same underlying sequence number, but only because this is a
synthetic dataset -- see the note in
[`src/datagen/keys.py`](https://github.com/henrymbuguak/erp-crm-reconciliation-pipeline/blob/main/src/datagen/keys.py)
suggesting a pipeline "could" match them by normalizing digits. The
reconciliation pipeline deliberately does **not** do this: a real legacy
migration has no such convenient correlation, so matching on it would be
pattern-matching a lucky detail of the test fixture rather than doing real
entity resolution. Instead, [`pipeline.resolve`](api.md#pipeline.resolve)
matches customers on fuzzy name similarity (`rapidfuzz`) combined with
normalized email/phone comparison, and matches invoices/payments on their
already-resolved customer/invoice plus date and amount proximity. Business
keys are still used, just only as stable identifiers _within_ a single
system, never as the cross-system join key.

### Crosswalk persistence and quarantine

`data/processed/crosswalk.json` is upserted (never overwritten) on every
`reconcile` run, keyed on `(entity_type, erp_key, crm_key)` so re-running on
unchanged input never duplicates a canonical entity -- see
[`pipeline.crosswalk`](api.md#pipeline.crosswalk). Every quarantined row is
written to `data/processed/quarantine_log.json` by
[`pipeline.quarantine`](api.md#pipeline.quarantine); an orphan is a valid
outcome and is never quarantined.
