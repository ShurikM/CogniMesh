MODEL (
  name gold_cognimesh.order_analytics,
  kind FULL,
  grain (dimension_type, dimension_value),
  description 'Consolidated order analytics across region, category, month, and cross-sell dimensions (UC-04,10,12,14,18,19)'
);

-- Region dimension (UC-04, UC-19)
SELECT
    'region' AS dimension_type,
    customer_region AS dimension_value,
    CAST(NULL AS TEXT) AS dimension_value_2,
    SUM(amount_usd) AS total_revenue,
    COALESCE(SUM(amount_usd)
        FILTER (WHERE created_at > now() - INTERVAL '30 days'), 0
    ) AS revenue_30d,
    COALESCE(SUM(amount_usd)
        FILTER (WHERE created_at > now() - INTERVAL '90 days'), 0
    ) AS revenue_90d,
    COUNT(*) AS order_count,
    COUNT(*) FILTER (
        WHERE created_at > now() - INTERVAL '30 days'
    ) AS order_count_30d,
    ROUND(AVG(amount_usd), 2) AS avg_order_value,
    CAST(NULL AS INTEGER) AS product_count,
    CAST(NULL AS NUMERIC) AS pct_of_total,
    CAST(NULL AS INTEGER) AS unique_customers,
    CAST(NULL AS INTEGER) AS co_purchase_count,
    CAST(NULL AS NUMERIC) AS co_purchase_pct,
    CASE
        WHEN COALESCE(SUM(amount_usd) FILTER (
            WHERE created_at BETWEEN now() - INTERVAL '60 days'
                                AND now() - INTERVAL '30 days'
        ), 0) > 0
        THEN ROUND(
            100.0 * (
                COALESCE(SUM(amount_usd) FILTER (
                    WHERE created_at > now() - INTERVAL '30 days'
                ), 0)
                - COALESCE(SUM(amount_usd) FILTER (
                    WHERE created_at BETWEEN now() - INTERVAL '60 days'
                                        AND now() - INTERVAL '30 days'
                ), 0)
            ) / GREATEST(
                COALESCE(SUM(amount_usd) FILTER (
                    WHERE created_at BETWEEN now() - INTERVAL '60 days'
                                        AND now() - INTERVAL '30 days'
                ), 0), 1
            ), 2
        )
        ELSE NULL
    END AS growth_pct
FROM silver.orders_enriched
WHERE status IN ('completed', 'pending')
GROUP BY customer_region

UNION ALL

-- Category dimension (UC-10, UC-12)
SELECT
    'category' AS dimension_type,
    product_category AS dimension_value,
    CAST(NULL AS TEXT) AS dimension_value_2,
    SUM(amount_usd) AS total_revenue,
    COALESCE(SUM(amount_usd)
        FILTER (WHERE created_at > now() - INTERVAL '30 days'), 0
    ) AS revenue_30d,
    CAST(NULL AS NUMERIC) AS revenue_90d,
    COUNT(*) AS order_count,
    COUNT(*) FILTER (
        WHERE created_at > now() - INTERVAL '30 days'
    ) AS order_count_30d,
    ROUND(AVG(amount_usd), 2) AS avg_order_value,
    COUNT(DISTINCT product_id) AS product_count,
    ROUND(
        100.0 * SUM(amount_usd)
        / GREATEST(SUM(SUM(amount_usd)) OVER (), 1), 2
    ) AS pct_of_total,
    CAST(NULL AS INTEGER) AS unique_customers,
    CAST(NULL AS INTEGER) AS co_purchase_count,
    CAST(NULL AS NUMERIC) AS co_purchase_pct,
    CAST(NULL AS NUMERIC) AS growth_pct
FROM silver.orders_enriched
WHERE status IN ('completed', 'pending')
GROUP BY product_category

UNION ALL

-- Month dimension (UC-14)
SELECT
    'month' AS dimension_type,
    DATE_TRUNC('month', created_at)::DATE::TEXT AS dimension_value,
    CAST(NULL AS TEXT) AS dimension_value_2,
    SUM(amount_usd) AS total_revenue,
    CAST(NULL AS NUMERIC) AS revenue_30d,
    CAST(NULL AS NUMERIC) AS revenue_90d,
    COUNT(*) AS order_count,
    CAST(NULL AS INTEGER) AS order_count_30d,
    ROUND(AVG(amount_usd), 2) AS avg_order_value,
    CAST(NULL AS INTEGER) AS product_count,
    CAST(NULL AS NUMERIC) AS pct_of_total,
    COUNT(DISTINCT customer_id) AS unique_customers,
    CAST(NULL AS INTEGER) AS co_purchase_count,
    CAST(NULL AS NUMERIC) AS co_purchase_pct,
    CAST(NULL AS NUMERIC) AS growth_pct
FROM silver.orders_enriched
WHERE status IN ('completed', 'pending')
GROUP BY DATE_TRUNC('month', created_at)

UNION ALL

-- Cross-sell dimension (UC-18)
SELECT
    'cross_sell' AS dimension_type,
    a.product_category AS dimension_value,
    b.product_category AS dimension_value_2,
    CAST(NULL AS NUMERIC) AS total_revenue,
    CAST(NULL AS NUMERIC) AS revenue_30d,
    CAST(NULL AS NUMERIC) AS revenue_90d,
    CAST(NULL AS INTEGER) AS order_count,
    CAST(NULL AS INTEGER) AS order_count_30d,
    CAST(NULL AS NUMERIC) AS avg_order_value,
    CAST(NULL AS INTEGER) AS product_count,
    CAST(NULL AS NUMERIC) AS pct_of_total,
    CAST(NULL AS INTEGER) AS unique_customers,
    COUNT(DISTINCT a.customer_id) AS co_purchase_count,
    ROUND(
        100.0 * COUNT(DISTINCT a.customer_id)
        / GREATEST(
            (SELECT COUNT(DISTINCT customer_id)
             FROM silver.orders_enriched
             WHERE product_category = a.product_category
               AND status IN ('completed', 'pending')),
            1
        ), 2
    ) AS co_purchase_pct,
    CAST(NULL AS NUMERIC) AS growth_pct
FROM silver.orders_enriched a
JOIN silver.orders_enriched b
    ON a.customer_id = b.customer_id
    AND a.product_category < b.product_category
    AND b.status IN ('completed', 'pending')
WHERE a.status IN ('completed', 'pending')
GROUP BY a.product_category, b.product_category
