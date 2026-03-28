-- CogniMesh Benchmark: Scale Schema (UC-04 through UC-20)
-- 17 new REST Gold tables + 4 CogniMesh consolidated Gold tables
-- Run AFTER schema.sql (depends on gold_rest / gold_cognimesh schemas)

-- ============================================================
-- GOLD (REST): Dedicated tables for UC-04 through UC-20
-- ============================================================

-- UC-04: Revenue by Region
CREATE TABLE IF NOT EXISTS gold_rest.revenue_by_region (
    region TEXT PRIMARY KEY,
    total_revenue NUMERIC(14,2) NOT NULL,
    order_count INTEGER NOT NULL,
    avg_order_value NUMERIC(10,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-05: Customer Lifetime Value
CREATE TABLE IF NOT EXISTS gold_rest.customer_ltv (
    customer_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    signup_date DATE NOT NULL,
    total_orders INTEGER NOT NULL,
    total_spend NUMERIC(12,2) NOT NULL,
    ltv_segment TEXT NOT NULL,
    months_active INTEGER NOT NULL,
    avg_monthly_spend NUMERIC(10,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-06: Purchase Frequency
CREATE TABLE IF NOT EXISTS gold_rest.purchase_frequency (
    customer_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    total_orders INTEGER NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    avg_days_between_orders NUMERIC(8,2),
    frequency_segment TEXT NOT NULL, -- frequent, regular, occasional, dormant
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-07: Regional Customer Distribution
CREATE TABLE IF NOT EXISTS gold_rest.regional_distribution (
    region TEXT PRIMARY KEY,
    customer_count INTEGER NOT NULL,
    avg_spend NUMERIC(10,2) NOT NULL,
    avg_orders NUMERIC(8,2) NOT NULL,
    pct_high_ltv NUMERIC(5,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-08: Product Return Analysis
CREATE TABLE IF NOT EXISTS gold_rest.product_returns (
    product_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    return_rate NUMERIC(5,4) NOT NULL,
    units_sold_30d INTEGER NOT NULL,
    returns_30d INTEGER NOT NULL,
    revenue_impact NUMERIC(12,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-09: Customer Spend Segmentation
CREATE TABLE IF NOT EXISTS gold_rest.spend_segments (
    customer_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    total_spend NUMERIC(12,2) NOT NULL,
    spend_segment TEXT NOT NULL, -- whale, high, medium, low, minimal
    percentile NUMERIC(5,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-10: Order Volume by Category
CREATE TABLE IF NOT EXISTS gold_rest.order_volume_category (
    category TEXT PRIMARY KEY,
    order_count_30d INTEGER NOT NULL,
    revenue_30d NUMERIC(12,2) NOT NULL,
    avg_order_value NUMERIC(10,2) NOT NULL,
    product_count INTEGER NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-11: Top Customers by Spend
CREATE TABLE IF NOT EXISTS gold_rest.top_customers (
    customer_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    total_spend NUMERIC(12,2) NOT NULL,
    total_orders INTEGER NOT NULL,
    ltv_segment TEXT NOT NULL,
    rank_overall INTEGER NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-12: Category Revenue Share
CREATE TABLE IF NOT EXISTS gold_rest.category_revenue (
    category TEXT PRIMARY KEY,
    total_revenue NUMERIC(14,2) NOT NULL,
    pct_of_total NUMERIC(5,2) NOT NULL,
    order_count INTEGER NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-13: Churn Prediction Inputs
CREATE TABLE IF NOT EXISTS gold_rest.churn_inputs (
    customer_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    total_orders INTEGER NOT NULL,
    total_spend NUMERIC(12,2) NOT NULL,
    ltv_segment TEXT NOT NULL,
    region TEXT NOT NULL,
    churn_risk_score NUMERIC(5,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-14: Monthly Revenue Trend
CREATE TABLE IF NOT EXISTS gold_rest.monthly_revenue (
    month DATE PRIMARY KEY,
    total_revenue NUMERIC(14,2) NOT NULL,
    order_count INTEGER NOT NULL,
    unique_customers INTEGER NOT NULL,
    avg_order_value NUMERIC(10,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-15: Customer Acquisition by Region
CREATE TABLE IF NOT EXISTS gold_rest.acquisition_by_region (
    region TEXT NOT NULL,
    signup_month DATE NOT NULL,
    new_customers INTEGER NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (region, signup_month)
);

-- UC-16: Low-Performing Products
CREATE TABLE IF NOT EXISTS gold_rest.low_performers (
    product_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    revenue_30d NUMERIC(12,2) NOT NULL,
    units_sold_30d INTEGER NOT NULL,
    return_rate NUMERIC(5,4) NOT NULL,
    performance_score NUMERIC(5,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-17: High-Value Customer Orders
CREATE TABLE IF NOT EXISTS gold_rest.high_value_orders (
    customer_id UUID NOT NULL,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    total_spend NUMERIC(12,2) NOT NULL,
    order_count INTEGER NOT NULL,
    avg_order_value NUMERIC(10,2) NOT NULL,
    ltv_segment TEXT NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (customer_id)
);

-- UC-18: Product Cross-Sell
CREATE TABLE IF NOT EXISTS gold_rest.cross_sell (
    product_category TEXT NOT NULL,
    co_category TEXT NOT NULL,
    co_purchase_count INTEGER NOT NULL,
    co_purchase_pct NUMERIC(5,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (product_category, co_category)
);

-- UC-19: Regional Revenue Comparison
CREATE TABLE IF NOT EXISTS gold_rest.regional_revenue (
    region TEXT PRIMARY KEY,
    revenue_30d NUMERIC(14,2) NOT NULL,
    revenue_90d NUMERIC(14,2) NOT NULL,
    growth_pct NUMERIC(6,2),
    order_count_30d INTEGER NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- UC-20: Customer Engagement Score
CREATE TABLE IF NOT EXISTS gold_rest.engagement_score (
    customer_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    total_orders INTEGER NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    total_spend NUMERIC(12,2) NOT NULL,
    engagement_score NUMERIC(5,2) NOT NULL, -- 0-100 composite
    engagement_tier TEXT NOT NULL, -- highly_engaged, engaged, passive, disengaged
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- GOLD (CogniMesh): Consolidated views for 20-UC scale
-- ============================================================

-- customer_360: serves UC-01,03,05,06,07,09,11,13,15,20
CREATE TABLE IF NOT EXISTS gold_cognimesh.customer_360 (
    customer_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    region TEXT NOT NULL,
    signup_date DATE NOT NULL,
    total_orders INTEGER NOT NULL,
    total_spend NUMERIC(12,2) NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    ltv_segment TEXT NOT NULL,
    health_status TEXT NOT NULL,
    risk_score NUMERIC(5,2) NOT NULL,
    months_active INTEGER NOT NULL,
    avg_monthly_spend NUMERIC(10,2) NOT NULL,
    avg_days_between_orders NUMERIC(8,2),
    frequency_segment TEXT NOT NULL,
    spend_segment TEXT NOT NULL,
    percentile NUMERIC(5,2) NOT NULL,
    rank_overall INTEGER NOT NULL,
    churn_risk_score NUMERIC(5,2) NOT NULL,
    engagement_score NUMERIC(5,2) NOT NULL,
    engagement_tier TEXT NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- product_catalog: serves UC-02,08,16
CREATE TABLE IF NOT EXISTS gold_cognimesh.product_catalog (
    product_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price NUMERIC(10,2) NOT NULL,
    units_sold_30d INTEGER NOT NULL,
    revenue_30d NUMERIC(12,2) NOT NULL,
    return_rate NUMERIC(5,4) NOT NULL,
    rank_in_category INTEGER NOT NULL,
    returns_30d INTEGER NOT NULL,
    revenue_impact NUMERIC(12,2) NOT NULL,
    performance_score NUMERIC(5,2) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);

-- order_analytics: serves UC-04,10,12,14,18,19
CREATE TABLE IF NOT EXISTS gold_cognimesh.order_analytics (
    id SERIAL PRIMARY KEY,
    dimension_type TEXT NOT NULL, -- region, category, month, cross_sell
    dimension_value TEXT NOT NULL,
    dimension_value_2 TEXT, -- for cross_sell pairs
    total_revenue NUMERIC(14,2),
    revenue_30d NUMERIC(14,2),
    revenue_90d NUMERIC(14,2),
    order_count INTEGER,
    order_count_30d INTEGER,
    avg_order_value NUMERIC(10,2),
    unique_customers INTEGER,
    product_count INTEGER,
    growth_pct NUMERIC(6,2),
    pct_of_total NUMERIC(5,2),
    co_purchase_count INTEGER,
    co_purchase_pct NUMERIC(5,2),
    computed_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(dimension_type, dimension_value, dimension_value_2)
);

-- customer_orders: serves UC-17
CREATE TABLE IF NOT EXISTS gold_cognimesh.customer_orders (
    customer_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    total_spend NUMERIC(12,2) NOT NULL,
    order_count INTEGER NOT NULL,
    avg_order_value NUMERIC(10,2) NOT NULL,
    ltv_segment TEXT NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now()
);
