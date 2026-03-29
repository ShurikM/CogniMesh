MODEL (
  name gold_cognimesh.customer_orders,
  kind FULL,
  grain customer_id,
  description 'High-value customer orders serving UC-17'
);

SELECT
    cp.customer_id,
    cp.name,
    cp.region,
    cp.total_spend,
    cp.total_orders AS order_count,
    CASE
        WHEN cp.total_orders > 0
            THEN ROUND(cp.total_spend / cp.total_orders, 2)
        ELSE 0
    END AS avg_order_value,
    cp.ltv_segment
FROM silver.customer_profiles cp
WHERE cp.ltv_segment IN ('high', 'medium')
