MODEL (
  name gold_cognimesh.product_catalog,
  kind FULL,
  grain product_id,
  description 'Consolidated product view serving UC-02,08,16'
);

SELECT
    pm.product_id,
    pm.name,
    pm.category,
    pm.price,
    pm.units_sold_30d,
    pm.revenue_30d,
    pm.return_rate,
    ROW_NUMBER() OVER (
        PARTITION BY pm.category ORDER BY pm.revenue_30d DESC
    ) AS rank_in_category,
    ROUND(pm.return_rate * pm.units_sold_30d)::INTEGER AS returns_30d,
    ROUND(pm.return_rate * pm.revenue_30d, 2) AS revenue_impact,
    ROUND(
        GREATEST(
            (1 - pm.return_rate) * 30
            + LEAST(pm.units_sold_30d::NUMERIC / 10, 40)
            + LEAST(pm.revenue_30d / 1000, 30),
            0
        ), 2
    ) AS performance_score
FROM silver.product_metrics pm
