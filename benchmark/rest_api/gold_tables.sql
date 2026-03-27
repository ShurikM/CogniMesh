-- Standalone SQL to populate REST Gold tables from Silver.
-- Same logic as benchmark/data/seed.py:populate_gold("gold_rest").

-- Customer health: join profiles with health-status classification
TRUNCATE gold_rest.customer_health;
INSERT INTO gold_rest.customer_health
    (customer_id, name, region,
     total_orders, total_spend,
     days_since_last_order, ltv_segment,
     health_status)
SELECT
    customer_id, name, region,
    total_orders, total_spend,
    days_since_last_order, ltv_segment,
    CASE
        WHEN days_since_last_order < 30
            AND ltv_segment IN ('high', 'medium')
            THEN 'healthy'
        WHEN days_since_last_order < 90
            THEN 'warning'
        ELSE 'critical'
    END
FROM silver.customer_profiles;

-- Top products: rank within category by 30-day revenue
TRUNCATE gold_rest.top_products;
INSERT INTO gold_rest.top_products
    (product_id, category, name, price,
     units_sold_30d, revenue_30d,
     return_rate, rank_in_category)
SELECT
    product_id, category, name, price,
    units_sold_30d, revenue_30d, return_rate,
    ROW_NUMBER() OVER (
        PARTITION BY category
        ORDER BY revenue_30d DESC
    )
FROM silver.product_metrics;

-- At-risk customers: high churn probability based on inactivity + LTV
TRUNCATE gold_rest.at_risk_customers;
INSERT INTO gold_rest.at_risk_customers
    (customer_id, name, region,
     days_since_last_order, ltv_segment,
     total_spend, risk_score)
SELECT
    customer_id, name, region,
    days_since_last_order, ltv_segment,
    total_spend,
    LEAST(
        (days_since_last_order::NUMERIC / 365) * 50
        + CASE ltv_segment
            WHEN 'high' THEN 30
            WHEN 'medium' THEN 15
            ELSE 5
          END,
        99.99
    )
FROM silver.customer_profiles
WHERE days_since_last_order > 60
   OR (ltv_segment IN ('high', 'medium')
       AND days_since_last_order > 30);
