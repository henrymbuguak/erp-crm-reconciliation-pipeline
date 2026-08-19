# Reconciliation Report

## Executive summary

- Total records ingested: 87
- Success rate (ingested, not quarantined): 90.8%
- Records quarantined: 8
- Execution time: 0.02s

## Records ingested per source system

| Source | Customers | Invoices | Payments |
| --- | --- | --- | --- |
| ERP | 8 | 19 | 17 |
| CRM | 8 | 19 | 16 |

## Match rate

| Entity | Matched | Total | Match rate |
| --- | --- | --- | --- |
| customer | 8 | 8 | 100.0% |
| invoice | 16 | 16 | 100.0% |
| payment | 12 | 19 | 63.2% |

## Quarantine breakdown

Total quarantined: 8

| Reason code | Count |
| --- | --- |
| unparseable_date | 5 |
| unrecoverable_encoding | 0 |
| missing_required_field | 3 |
| schema_invalid | 0 |
| ambiguous_match | 0 |

## Orphans (records with no counterpart in the other system)

### Customer

ERP-only: 0

_none_

CRM-only: 0

_none_

### Invoice

ERP-only: 0

_none_

CRM-only: 0

_none_

### Payment

ERP-only: 4

- `erp_key=PMT-000001` `crm_key=None`
- `erp_key=PMT-000003` `crm_key=None`
- `erp_key=PMT-000004` `crm_key=None`
- `erp_key=PMT-000008` `crm_key=None`

CRM-only: 3

- `erp_key=None` `crm_key=PAY000001`
- `erp_key=None` `crm_key=PAY000003`
- `erp_key=None` `crm_key=PAY000008`

## Payment amount mismatches

Mismatched payments: 0

Total drift: 0


## Intra-system duplicates collapsed

Duplicate groups collapsed: 0

_none_
