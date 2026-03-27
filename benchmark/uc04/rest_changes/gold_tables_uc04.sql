-- UC-04: Revenue by Region (last 30 days)
-- REST approach: new Gold table + new endpoint required

CREATE TABLE IF NOT EXISTS gold_rest.revenue_by_region (
    region              TEXT PRIMARY KEY,
    total_revenue       NUMERIC(14,2) NOT NULL,
    order_count         INTEGER NOT NULL,
    avg_order_value     NUMERIC(10,2) NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Populate from Silver
INSERT INTO gold_rest.revenue_by_region (region, total_revenue, order_count, avg_order_value)
SELECT
    customer_region AS region,
    SUM(amount_usd) AS total_revenue,
    COUNT(*) AS order_count,
    AVG(amount_usd) AS avg_order_value
FROM silver.orders_enriched
WHERE created_at > now() - INTERVAL '30 days'
  AND status = 'completed'
GROUP BY customer_region
ON CONFLICT (region) DO UPDATE SET
    total_revenue = EXCLUDED.total_revenue,
    order_count = EXCLUDED.order_count,
    avg_order_value = EXCLUDED.avg_order_value,
    computed_at = now();
