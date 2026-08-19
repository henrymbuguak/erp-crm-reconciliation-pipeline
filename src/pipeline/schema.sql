-- Postgres target schema for the ERP/CRM reconciliation pipeline.
--
-- `customers` / `invoices` / `payments` store the post-cleaning,
-- per-source-system projection (see `pipeline.models.Clean*`). `crosswalk`
-- and `quarantine_log` mirror `data/processed/crosswalk.json` and
-- `quarantine_log.json` exactly -- this schema is an additional
-- persistence layer, not a replacement; the JSON files remain the source
-- of truth `reconcile run` reads back on the next invocation.
--
-- Requires Postgres 15+ for `UNIQUE NULLS NOT DISTINCT`.

CREATE TABLE IF NOT EXISTS customers (
    source_system TEXT NOT NULL CHECK (source_system IN ('erp', 'crm')),
    business_key  TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    email         TEXT,
    phone         TEXT,
    street        TEXT,
    city          TEXT,
    region        TEXT,
    postal_code   TEXT,
    country       TEXT,
    created_at    DATE,
    PRIMARY KEY (source_system, business_key)
);

CREATE TABLE IF NOT EXISTS invoices (
    source_system         TEXT NOT NULL CHECK (source_system IN ('erp', 'crm')),
    business_key          TEXT NOT NULL,
    customer_business_key TEXT NOT NULL,
    issue_date            DATE NOT NULL,
    due_date              DATE,
    currency              TEXT NOT NULL,
    amount                NUMERIC(14, 2) NOT NULL,
    status                TEXT,
    PRIMARY KEY (source_system, business_key)
);

CREATE TABLE IF NOT EXISTS payments (
    source_system        TEXT NOT NULL CHECK (source_system IN ('erp', 'crm')),
    business_key         TEXT NOT NULL,
    invoice_business_key TEXT NOT NULL,
    payment_date         DATE NOT NULL,
    amount               NUMERIC(14, 2) NOT NULL,
    method               TEXT,
    PRIMARY KEY (source_system, business_key)
);

-- Keyed on (entity_type, erp_key, crm_key), matching crosswalk.json -- see
-- pipeline.crosswalk's module docstring for the reject-on-conflict upsert
-- strategy and its known re-run limitation. NULLS NOT DISTINCT makes two
-- NULLs compare equal for this constraint, matching Python tuple equality
-- (JSON) semantics -- every entry has at least one non-null key, enforced
-- below, so this never collapses two genuinely different entities.
CREATE TABLE IF NOT EXISTS crosswalk (
    entity_type  TEXT NOT NULL CHECK (entity_type IN ('customer', 'invoice', 'payment')),
    canonical_id UUID NOT NULL UNIQUE,
    erp_key      TEXT,
    crm_key      TEXT,
    CHECK (erp_key IS NOT NULL OR crm_key IS NOT NULL),
    UNIQUE NULLS NOT DISTINCT (entity_type, erp_key, crm_key)
);

-- Replaced in full on every `reconcile run`, matching
-- quarantine_log.json's overwrite (not upsert) behavior -- this table
-- reflects only the most recent run's failures, not cumulative history.
CREATE TABLE IF NOT EXISTS quarantine_log (
    id            BIGSERIAL PRIMARY KEY,
    entity_type   TEXT NOT NULL CHECK (entity_type IN ('customer', 'invoice', 'payment')),
    source_system TEXT NOT NULL CHECK (source_system IN ('erp', 'crm')),
    reason_code   TEXT NOT NULL,
    stage         TEXT NOT NULL,
    original_data JSONB NOT NULL
);
