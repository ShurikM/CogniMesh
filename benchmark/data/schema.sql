-- CogniMesh Benchmark Schema
-- Five schemas modeling the medallion architecture + CogniMesh internals

-- ============================================================
-- BRONZE: Raw ingested data
-- ============================================================
CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE bronze.customers (
    customer_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    email           TEXT NOT NULL,
    signup_date     DATE NOT NULL,
    region          TEXT NOT NULL  -- NA, EMEA, APAC, LATAM, MEA
);

CREATE TABLE bronze.products (
    product_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,  -- electronics, clothing, home, sports, books, food, toys, beauty
    price           NUMERIC(10,2) NOT NULL,
    supplier_id     UUID NOT NULL
);

CREATE TABLE bronze.orders (
    order_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     UUID NOT NULL REFERENCES bronze.customers(customer_id),
    product_id      UUID NOT NULL REFERENCES bronze.products(product_id),
    amount          NUMERIC(10,2) NOT NULL,
    status          TEXT NOT NULL,  -- completed, pending, refunded, cancelled
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_orders_customer ON bronze.orders(customer_id);
CREATE INDEX idx_orders_product ON bronze.orders(product_id);
CREATE INDEX idx_orders_created ON bronze.orders(created_at);

-- ============================================================
-- SILVER: Cleaned, enriched, normalized
-- ============================================================
CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE silver.customer_profiles (
    customer_id         UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    email               TEXT NOT NULL,
    region              TEXT NOT NULL,
    signup_date         DATE NOT NULL,
    total_orders        INTEGER NOT NULL DEFAULT 0,
    total_spend         NUMERIC(12,2) NOT NULL DEFAULT 0,
    days_since_last_order INTEGER NOT NULL DEFAULT 0,
    ltv_segment         TEXT NOT NULL DEFAULT 'low',  -- high, medium, low
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE silver.product_metrics (
    product_id          UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    category            TEXT NOT NULL,
    price               NUMERIC(10,2) NOT NULL,
    units_sold_30d      INTEGER NOT NULL DEFAULT 0,
    revenue_30d         NUMERIC(12,2) NOT NULL DEFAULT 0,
    return_rate         NUMERIC(5,4) NOT NULL DEFAULT 0,
    stock_status        TEXT NOT NULL DEFAULT 'in_stock',  -- in_stock, low_stock, out_of_stock
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE silver.orders_enriched (
    order_id            UUID PRIMARY KEY,
    customer_id         UUID NOT NULL,
    product_id          UUID NOT NULL,
    customer_region     TEXT NOT NULL,
    product_category    TEXT NOT NULL,
    amount_usd          NUMERIC(10,2) NOT NULL,
    status              TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_enriched_region ON silver.orders_enriched(customer_region);
CREATE INDEX idx_enriched_category ON silver.orders_enriched(product_category);
CREATE INDEX idx_enriched_created ON silver.orders_enriched(created_at);
CREATE INDEX idx_enriched_customer ON silver.orders_enriched(customer_id);
CREATE INDEX idx_enriched_customer_status ON silver.orders_enriched(customer_id, status);

-- ============================================================
-- GOLD (REST): Hand-designed, dedicated tables
-- ============================================================
CREATE SCHEMA IF NOT EXISTS gold_rest;

CREATE TABLE gold_rest.customer_health (
    customer_id         UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    region              TEXT NOT NULL,
    total_orders        INTEGER NOT NULL,
    total_spend         NUMERIC(12,2) NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    ltv_segment         TEXT NOT NULL,
    health_status       TEXT NOT NULL,  -- healthy, warning, critical
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gold_rest.top_products (
    product_id          UUID NOT NULL,
    category            TEXT NOT NULL,
    name                TEXT NOT NULL,
    price               NUMERIC(10,2) NOT NULL,
    units_sold_30d      INTEGER NOT NULL,
    revenue_30d         NUMERIC(12,2) NOT NULL,
    return_rate         NUMERIC(5,4) NOT NULL,
    rank_in_category    INTEGER NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (category, rank_in_category)
);

CREATE TABLE gold_rest.at_risk_customers (
    customer_id         UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    region              TEXT NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    ltv_segment         TEXT NOT NULL,
    total_spend         NUMERIC(12,2) NOT NULL,
    risk_score          NUMERIC(5,2) NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- GOLD (CogniMesh): Derived from UC definitions
-- ============================================================
CREATE SCHEMA IF NOT EXISTS gold_cognimesh;

CREATE TABLE gold_cognimesh.customer_health (
    customer_id         UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    region              TEXT NOT NULL,
    total_orders        INTEGER NOT NULL,
    total_spend         NUMERIC(12,2) NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    ltv_segment         TEXT NOT NULL,
    health_status       TEXT NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gold_cognimesh.top_products (
    product_id          UUID NOT NULL,
    category            TEXT NOT NULL,
    name                TEXT NOT NULL,
    price               NUMERIC(10,2) NOT NULL,
    units_sold_30d      INTEGER NOT NULL,
    revenue_30d         NUMERIC(12,2) NOT NULL,
    return_rate         NUMERIC(5,4) NOT NULL,
    rank_in_category    INTEGER NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (category, rank_in_category)
);

CREATE TABLE gold_cognimesh.at_risk_customers (
    customer_id         UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    region              TEXT NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    ltv_segment         TEXT NOT NULL,
    total_spend         NUMERIC(12,2) NOT NULL,
    risk_score          NUMERIC(5,2) NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- COGNIMESH INTERNAL: Registry, audit, lineage, freshness
-- ============================================================
CREATE SCHEMA IF NOT EXISTS cognimesh_internal;

CREATE TABLE cognimesh_internal.uc_registry (
    id                  TEXT PRIMARY KEY,
    question            TEXT NOT NULL,
    consuming_agent     TEXT,
    required_fields     JSONB NOT NULL,
    access_pattern      TEXT NOT NULL,  -- individual_lookup, bulk_query, aggregation
    freshness_ttl_seconds INTEGER NOT NULL,
    gold_view           TEXT,  -- schema.table reference
    gold_schema         TEXT NOT NULL DEFAULT 'gold_cognimesh',
    source_tables       JSONB,  -- list of Silver source tables
    derivation_sql      TEXT,  -- SQL used to derive Gold from Silver
    status              TEXT NOT NULL DEFAULT 'active',
    allowed_agents      JSONB,  -- list of agent IDs allowed to query this UC. NULL = open access
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cognimesh_internal.audit_log (
    id                  BIGSERIAL PRIMARY KEY,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    uc_id               TEXT,
    tier                TEXT NOT NULL,  -- T0, T1, T2, T3
    query_text          TEXT,
    composed_sql        TEXT,  -- for T2: the generated SQL
    latency_ms          NUMERIC(10,2) NOT NULL,
    rows_returned       INTEGER NOT NULL DEFAULT 0,
    agent_id            TEXT,
    cost_units          NUMERIC(10,2) DEFAULT 0,
    metadata            JSONB DEFAULT '{}'
);

CREATE INDEX idx_audit_uc ON cognimesh_internal.audit_log(uc_id);
CREATE INDEX idx_audit_tier ON cognimesh_internal.audit_log(tier);
CREATE INDEX idx_audit_agent ON cognimesh_internal.audit_log(agent_id);
CREATE INDEX idx_audit_ts ON cognimesh_internal.audit_log(timestamp);

CREATE TABLE cognimesh_internal.lineage (
    id                  BIGSERIAL PRIMARY KEY,
    gold_view           TEXT NOT NULL,
    gold_column         TEXT NOT NULL,
    source_table        TEXT NOT NULL,
    source_column       TEXT NOT NULL,
    transformation      TEXT,  -- direct, aggregation:sum, filter, join, computed
    model_version       TEXT,
    registered_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (gold_view, gold_column, source_table, source_column)
);

CREATE INDEX idx_lineage_view ON cognimesh_internal.lineage(gold_view);

CREATE TABLE cognimesh_internal.freshness (
    gold_view           TEXT PRIMARY KEY,
    uc_id               TEXT NOT NULL,
    last_refreshed_at   TIMESTAMPTZ,
    ttl_seconds         INTEGER NOT NULL,
    row_count           INTEGER DEFAULT 0,
    refresh_duration_ms NUMERIC(10,2),
    CONSTRAINT fk_uc FOREIGN KEY (uc_id) REFERENCES cognimesh_internal.uc_registry(id)
);

CREATE TABLE cognimesh_internal.uc_change_log (
    id                  BIGSERIAL PRIMARY KEY,
    uc_id               TEXT NOT NULL,
    change_type         TEXT NOT NULL,  -- created, updated, deactivated
    before_state        JSONB,
    after_state         JSONB,
    changed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by          TEXT
);

CREATE TABLE cognimesh_internal.approval_queue (
    id                  BIGSERIAL PRIMARY KEY,
    uc_id               TEXT NOT NULL,
    action              TEXT NOT NULL,  -- register, update, deactivate, refresh
    status              TEXT NOT NULL DEFAULT 'pending',  -- pending, approved, rejected
    request_data        JSONB NOT NULL,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    requested_by        TEXT,
    reviewed_by         TEXT,
    reviewed_at         TIMESTAMPTZ,
    review_note         TEXT
);

CREATE INDEX idx_approval_status ON cognimesh_internal.approval_queue(status);
CREATE INDEX idx_approval_uc ON cognimesh_internal.approval_queue(uc_id);
