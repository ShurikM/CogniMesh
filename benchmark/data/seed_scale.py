"""
CogniMesh Benchmark: Scale Seed (UC-04 through UC-20)

Creates the 17 new REST Gold tables + 4 CogniMesh consolidated Gold tables,
populates them from Silver, and prints row counts and storage sizes.

Run: uv run python benchmark/data/seed_scale.py
"""

import logging
import os
import time
from pathlib import Path

import psycopg  # type: ignore[import-untyped]
from psycopg import sql as pgsql  # type: ignore[import-untyped]

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://cognimesh:cognimesh@localhost:5432/cognimesh_bench",
)

log = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).parent / "schema_scale.sql"


def _qualified_id(schema_dot_table: str) -> pgsql.Composed:
    """Return a safe psycopg sql.Identifier for 'schema.table' strings."""
    schema_name, table_name = schema_dot_table.split(".", 1)
    return pgsql.Identifier(schema_name, table_name)


# ============================================================
# REST Gold table derivation SQL (UC-04 through UC-20)
# ============================================================

_REST_TABLES: list[tuple[str, str]] = [
    # UC-04: Revenue by Region
    (
        "gold_rest.revenue_by_region",
        """
        INSERT INTO gold_rest.revenue_by_region
            (region, total_revenue, order_count, avg_order_value)
        SELECT
            customer_region AS region,
            SUM(amount_usd) AS total_revenue,
            COUNT(*) AS order_count,
            ROUND(AVG(amount_usd), 2) AS avg_order_value
        FROM silver.orders_enriched
        WHERE status IN ('completed', 'pending')
        GROUP BY customer_region
        """,
    ),
    # UC-05: Customer Lifetime Value
    (
        "gold_rest.customer_ltv",
        """
        INSERT INTO gold_rest.customer_ltv
            (customer_id, name, region, signup_date, total_orders,
             total_spend, ltv_segment, months_active, avg_monthly_spend)
        SELECT
            cp.customer_id, cp.name, cp.region, cp.signup_date,
            cp.total_orders, cp.total_spend, cp.ltv_segment,
            GREATEST(
                EXTRACT(YEAR FROM AGE(now(), cp.signup_date)) * 12
                + EXTRACT(MONTH FROM AGE(now(), cp.signup_date)),
                1
            )::INTEGER AS months_active,
            ROUND(
                cp.total_spend / GREATEST(
                    EXTRACT(YEAR FROM AGE(now(), cp.signup_date)) * 12
                    + EXTRACT(MONTH FROM AGE(now(), cp.signup_date)),
                    1
                )::NUMERIC, 2
            ) AS avg_monthly_spend
        FROM silver.customer_profiles cp
        """,
    ),
    # UC-06: Purchase Frequency
    (
        "gold_rest.purchase_frequency",
        """
        INSERT INTO gold_rest.purchase_frequency
            (customer_id, name, total_orders, days_since_last_order,
             avg_days_between_orders, frequency_segment)
        SELECT
            cp.customer_id, cp.name, cp.total_orders,
            cp.days_since_last_order,
            CASE
                WHEN cp.total_orders > 1
                    THEN ROUND(
                        cp.days_since_last_order::NUMERIC
                        / GREATEST(cp.total_orders - 1, 1), 2
                    )
                ELSE NULL
            END AS avg_days_between_orders,
            CASE
                WHEN cp.total_orders >= 20 THEN 'frequent'
                WHEN cp.total_orders >= 10 THEN 'regular'
                WHEN cp.total_orders >= 3  THEN 'occasional'
                ELSE 'dormant'
            END AS frequency_segment
        FROM silver.customer_profiles cp
        """,
    ),
    # UC-07: Regional Customer Distribution
    (
        "gold_rest.regional_distribution",
        """
        INSERT INTO gold_rest.regional_distribution
            (region, customer_count, avg_spend, avg_orders, pct_high_ltv)
        SELECT
            region,
            COUNT(*) AS customer_count,
            ROUND(AVG(total_spend), 2) AS avg_spend,
            ROUND(AVG(total_orders), 2) AS avg_orders,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE ltv_segment = 'high')
                / GREATEST(COUNT(*), 1), 2
            ) AS pct_high_ltv
        FROM silver.customer_profiles
        GROUP BY region
        """,
    ),
    # UC-08: Product Return Analysis
    (
        "gold_rest.product_returns",
        """
        INSERT INTO gold_rest.product_returns
            (product_id, name, category, return_rate, units_sold_30d,
             returns_30d, revenue_impact)
        SELECT
            pm.product_id, pm.name, pm.category, pm.return_rate,
            pm.units_sold_30d,
            ROUND(pm.return_rate * pm.units_sold_30d)::INTEGER AS returns_30d,
            ROUND(pm.return_rate * pm.revenue_30d, 2) AS revenue_impact
        FROM silver.product_metrics pm
        """,
    ),
    # UC-09: Customer Spend Segmentation
    (
        "gold_rest.spend_segments",
        """
        INSERT INTO gold_rest.spend_segments
            (customer_id, name, region, total_spend, spend_segment, percentile)
        SELECT
            customer_id, name, region, total_spend,
            CASE
                WHEN pctl >= 95 THEN 'whale'
                WHEN pctl >= 80 THEN 'high'
                WHEN pctl >= 50 THEN 'medium'
                WHEN pctl >= 20 THEN 'low'
                ELSE 'minimal'
            END AS spend_segment,
            pctl AS percentile
        FROM (
            SELECT
                customer_id, name, region, total_spend,
                ROUND(
                    (PERCENT_RANK() OVER (ORDER BY total_spend) * 100)::NUMERIC, 2
                ) AS pctl
            FROM silver.customer_profiles
        ) sub
        """,
    ),
    # UC-10: Order Volume by Category
    (
        "gold_rest.order_volume_category",
        """
        INSERT INTO gold_rest.order_volume_category
            (category, order_count_30d, revenue_30d, avg_order_value,
             product_count)
        SELECT
            oe.product_category AS category,
            COUNT(*) AS order_count_30d,
            SUM(oe.amount_usd) AS revenue_30d,
            ROUND(AVG(oe.amount_usd), 2) AS avg_order_value,
            COUNT(DISTINCT oe.product_id) AS product_count
        FROM silver.orders_enriched oe
        WHERE oe.created_at > now() - INTERVAL '30 days'
          AND oe.status IN ('completed', 'pending')
        GROUP BY oe.product_category
        """,
    ),
    # UC-11: Top Customers by Spend
    (
        "gold_rest.top_customers",
        """
        INSERT INTO gold_rest.top_customers
            (customer_id, name, region, total_spend, total_orders,
             ltv_segment, rank_overall)
        SELECT
            customer_id, name, region, total_spend, total_orders,
            ltv_segment,
            ROW_NUMBER() OVER (ORDER BY total_spend DESC) AS rank_overall
        FROM silver.customer_profiles
        """,
    ),
    # UC-12: Category Revenue Share
    (
        "gold_rest.category_revenue",
        """
        INSERT INTO gold_rest.category_revenue
            (category, total_revenue, pct_of_total, order_count)
        SELECT
            product_category AS category,
            SUM(amount_usd) AS total_revenue,
            ROUND(
                100.0 * SUM(amount_usd)
                / GREATEST(SUM(SUM(amount_usd)) OVER (), 1), 2
            ) AS pct_of_total,
            COUNT(*) AS order_count
        FROM silver.orders_enriched
        WHERE status IN ('completed', 'pending')
        GROUP BY product_category
        """,
    ),
    # UC-13: Churn Prediction Inputs
    (
        "gold_rest.churn_inputs",
        """
        INSERT INTO gold_rest.churn_inputs
            (customer_id, name, days_since_last_order, total_orders,
             total_spend, ltv_segment, region, churn_risk_score)
        SELECT
            customer_id, name, days_since_last_order,
            total_orders, total_spend, ltv_segment, region,
            LEAST(
                ROUND(
                    (days_since_last_order::NUMERIC / 365) * 40
                    + CASE ltv_segment
                        WHEN 'high' THEN 30
                        WHEN 'medium' THEN 15
                        ELSE 5
                      END
                    + CASE
                        WHEN total_orders <= 1 THEN 20
                        WHEN total_orders <= 5 THEN 10
                        ELSE 0
                      END,
                    2
                ),
                99.99
            ) AS churn_risk_score
        FROM silver.customer_profiles
        """,
    ),
    # UC-14: Monthly Revenue Trend
    (
        "gold_rest.monthly_revenue",
        """
        INSERT INTO gold_rest.monthly_revenue
            (month, total_revenue, order_count, unique_customers,
             avg_order_value)
        SELECT
            DATE_TRUNC('month', created_at)::DATE AS month,
            SUM(amount_usd) AS total_revenue,
            COUNT(*) AS order_count,
            COUNT(DISTINCT customer_id) AS unique_customers,
            ROUND(AVG(amount_usd), 2) AS avg_order_value
        FROM silver.orders_enriched
        WHERE status IN ('completed', 'pending')
        GROUP BY DATE_TRUNC('month', created_at)
        ORDER BY month
        """,
    ),
    # UC-15: Customer Acquisition by Region
    (
        "gold_rest.acquisition_by_region",
        """
        INSERT INTO gold_rest.acquisition_by_region
            (region, signup_month, new_customers)
        SELECT
            region,
            DATE_TRUNC('month', signup_date)::DATE AS signup_month,
            COUNT(*) AS new_customers
        FROM silver.customer_profiles
        GROUP BY region, DATE_TRUNC('month', signup_date)
        """,
    ),
    # UC-16: Low-Performing Products
    (
        "gold_rest.low_performers",
        """
        INSERT INTO gold_rest.low_performers
            (product_id, name, category, revenue_30d, units_sold_30d,
             return_rate, performance_score)
        SELECT
            product_id, name, category, revenue_30d, units_sold_30d,
            return_rate,
            ROUND(
                GREATEST(
                    (1 - return_rate) * 30
                    + LEAST(units_sold_30d::NUMERIC / 10, 40)
                    + LEAST(revenue_30d / 1000, 30),
                    0
                ), 2
            ) AS performance_score
        FROM silver.product_metrics
        """,
    ),
    # UC-17: High-Value Customer Orders
    (
        "gold_rest.high_value_orders",
        """
        INSERT INTO gold_rest.high_value_orders
            (customer_id, name, region, total_spend, order_count,
             avg_order_value, ltv_segment)
        SELECT
            cp.customer_id, cp.name, cp.region, cp.total_spend,
            cp.total_orders AS order_count,
            CASE
                WHEN cp.total_orders > 0
                    THEN ROUND(cp.total_spend / cp.total_orders, 2)
                ELSE 0
            END AS avg_order_value,
            cp.ltv_segment
        FROM silver.customer_profiles cp
        WHERE cp.ltv_segment IN ('high', 'medium')
        """,
    ),
    # UC-18: Product Cross-Sell
    (
        "gold_rest.cross_sell",
        """
        INSERT INTO gold_rest.cross_sell
            (product_category, co_category, co_purchase_count,
             co_purchase_pct)
        SELECT
            a.product_category,
            b.product_category AS co_category,
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
            ) AS co_purchase_pct
        FROM silver.orders_enriched a
        JOIN silver.orders_enriched b
            ON a.customer_id = b.customer_id
            AND a.product_category < b.product_category
            AND b.status IN ('completed', 'pending')
        WHERE a.status IN ('completed', 'pending')
        GROUP BY a.product_category, b.product_category
        """,
    ),
    # UC-19: Regional Revenue Comparison
    (
        "gold_rest.regional_revenue",
        """
        INSERT INTO gold_rest.regional_revenue
            (region, revenue_30d, revenue_90d, growth_pct, order_count_30d)
        SELECT
            customer_region AS region,
            COALESCE(SUM(amount_usd)
                FILTER (WHERE created_at > now() - INTERVAL '30 days'), 0
            ) AS revenue_30d,
            COALESCE(SUM(amount_usd)
                FILTER (WHERE created_at > now() - INTERVAL '90 days'), 0
            ) AS revenue_90d,
            CASE
                WHEN COALESCE(SUM(amount_usd) FILTER (
                    WHERE created_at BETWEEN now() - INTERVAL '90 days'
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
            END AS growth_pct,
            COUNT(*) FILTER (
                WHERE created_at > now() - INTERVAL '30 days'
            ) AS order_count_30d
        FROM silver.orders_enriched
        WHERE status IN ('completed', 'pending')
        GROUP BY customer_region
        """,
    ),
    # UC-20: Customer Engagement Score
    (
        "gold_rest.engagement_score",
        """
        INSERT INTO gold_rest.engagement_score
            (customer_id, name, region, total_orders,
             days_since_last_order, total_spend,
             engagement_score, engagement_tier)
        SELECT
            customer_id, name, region, total_orders,
            days_since_last_order, total_spend,
            LEAST(
                ROUND(
                    LEAST(total_orders::NUMERIC / 0.5, 40)
                    + GREATEST(40 - (days_since_last_order::NUMERIC / 9), 0)
                    + LEAST(total_spend / 500, 20),
                    2
                ),
                100
            ) AS engagement_score,
            CASE
                WHEN LEAST(
                    ROUND(
                        LEAST(total_orders::NUMERIC / 0.5, 40)
                        + GREATEST(40 - (days_since_last_order::NUMERIC / 9), 0)
                        + LEAST(total_spend / 500, 20),
                        2
                    ), 100
                ) >= 75 THEN 'highly_engaged'
                WHEN LEAST(
                    ROUND(
                        LEAST(total_orders::NUMERIC / 0.5, 40)
                        + GREATEST(40 - (days_since_last_order::NUMERIC / 9), 0)
                        + LEAST(total_spend / 500, 20),
                        2
                    ), 100
                ) >= 50 THEN 'engaged'
                WHEN LEAST(
                    ROUND(
                        LEAST(total_orders::NUMERIC / 0.5, 40)
                        + GREATEST(40 - (days_since_last_order::NUMERIC / 9), 0)
                        + LEAST(total_spend / 500, 20),
                        2
                    ), 100
                ) >= 25 THEN 'passive'
                ELSE 'disengaged'
            END AS engagement_tier
        FROM silver.customer_profiles
        """,
    ),
]

# ============================================================
# CogniMesh consolidated Gold table derivation SQL
# ============================================================

_COGNIMESH_TABLES: list[tuple[str, str]] = [
    # customer_360: serves UC-01,03,05,06,07,09,11,13,15,20
    (
        "gold_cognimesh.customer_360",
        """
        INSERT INTO gold_cognimesh.customer_360
            (customer_id, name, email, region, signup_date,
             total_orders, total_spend, days_since_last_order,
             ltv_segment, health_status, risk_score,
             months_active, avg_monthly_spend,
             avg_days_between_orders, frequency_segment,
             spend_segment, percentile, rank_overall,
             churn_risk_score, engagement_score, engagement_tier)
        SELECT
            cp.customer_id, cp.name, cp.email, cp.region, cp.signup_date,
            cp.total_orders, cp.total_spend, cp.days_since_last_order,
            cp.ltv_segment,
            -- health_status
            CASE
                WHEN cp.days_since_last_order < 30
                    AND cp.ltv_segment IN ('high', 'medium')
                    THEN 'healthy'
                WHEN cp.days_since_last_order < 90
                    THEN 'warning'
                ELSE 'critical'
            END AS health_status,
            -- risk_score
            LEAST(
                (cp.days_since_last_order::NUMERIC / 365) * 50
                + CASE cp.ltv_segment
                    WHEN 'high' THEN 30
                    WHEN 'medium' THEN 15
                    ELSE 5
                  END,
                99.99
            ) AS risk_score,
            -- months_active
            GREATEST(
                EXTRACT(YEAR FROM AGE(now(), cp.signup_date)) * 12
                + EXTRACT(MONTH FROM AGE(now(), cp.signup_date)),
                1
            )::INTEGER AS months_active,
            -- avg_monthly_spend
            ROUND(
                cp.total_spend / GREATEST(
                    EXTRACT(YEAR FROM AGE(now(), cp.signup_date)) * 12
                    + EXTRACT(MONTH FROM AGE(now(), cp.signup_date)),
                    1
                )::NUMERIC, 2
            ) AS avg_monthly_spend,
            -- avg_days_between_orders
            CASE
                WHEN cp.total_orders > 1
                    THEN ROUND(
                        cp.days_since_last_order::NUMERIC
                        / GREATEST(cp.total_orders - 1, 1), 2
                    )
                ELSE NULL
            END AS avg_days_between_orders,
            -- frequency_segment
            CASE
                WHEN cp.total_orders >= 20 THEN 'frequent'
                WHEN cp.total_orders >= 10 THEN 'regular'
                WHEN cp.total_orders >= 3  THEN 'occasional'
                ELSE 'dormant'
            END AS frequency_segment,
            -- spend_segment
            CASE
                WHEN pctl >= 95 THEN 'whale'
                WHEN pctl >= 80 THEN 'high'
                WHEN pctl >= 50 THEN 'medium'
                WHEN pctl >= 20 THEN 'low'
                ELSE 'minimal'
            END AS spend_segment,
            -- percentile
            pctl AS percentile,
            -- rank_overall
            ROW_NUMBER() OVER (ORDER BY cp.total_spend DESC)
                AS rank_overall,
            -- churn_risk_score
            LEAST(
                ROUND(
                    (cp.days_since_last_order::NUMERIC / 365) * 40
                    + CASE cp.ltv_segment
                        WHEN 'high' THEN 30
                        WHEN 'medium' THEN 15
                        ELSE 5
                      END
                    + CASE
                        WHEN cp.total_orders <= 1 THEN 20
                        WHEN cp.total_orders <= 5 THEN 10
                        ELSE 0
                      END,
                    2
                ),
                99.99
            ) AS churn_risk_score,
            -- engagement_score
            LEAST(
                ROUND(
                    LEAST(cp.total_orders::NUMERIC / 0.5, 40)
                    + GREATEST(40 - (cp.days_since_last_order::NUMERIC / 9), 0)
                    + LEAST(cp.total_spend / 500, 20),
                    2
                ),
                100
            ) AS engagement_score,
            -- engagement_tier
            CASE
                WHEN LEAST(
                    ROUND(
                        LEAST(cp.total_orders::NUMERIC / 0.5, 40)
                        + GREATEST(40 - (cp.days_since_last_order::NUMERIC / 9), 0)
                        + LEAST(cp.total_spend / 500, 20),
                        2
                    ), 100
                ) >= 75 THEN 'highly_engaged'
                WHEN LEAST(
                    ROUND(
                        LEAST(cp.total_orders::NUMERIC / 0.5, 40)
                        + GREATEST(40 - (cp.days_since_last_order::NUMERIC / 9), 0)
                        + LEAST(cp.total_spend / 500, 20),
                        2
                    ), 100
                ) >= 50 THEN 'engaged'
                WHEN LEAST(
                    ROUND(
                        LEAST(cp.total_orders::NUMERIC / 0.5, 40)
                        + GREATEST(40 - (cp.days_since_last_order::NUMERIC / 9), 0)
                        + LEAST(cp.total_spend / 500, 20),
                        2
                    ), 100
                ) >= 25 THEN 'passive'
                ELSE 'disengaged'
            END AS engagement_tier
        FROM (
            SELECT
                cp.*,
                ROUND(
                    (PERCENT_RANK() OVER (ORDER BY cp.total_spend) * 100)::NUMERIC, 2
                ) AS pctl
            FROM silver.customer_profiles cp
        ) cp
        """,
    ),
    # product_catalog: serves UC-02,08,16
    (
        "gold_cognimesh.product_catalog",
        """
        INSERT INTO gold_cognimesh.product_catalog
            (product_id, name, category, price, units_sold_30d,
             revenue_30d, return_rate, rank_in_category,
             returns_30d, revenue_impact, performance_score)
        SELECT
            pm.product_id, pm.name, pm.category, pm.price,
            pm.units_sold_30d, pm.revenue_30d, pm.return_rate,
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
        """,
    ),
    # order_analytics (region dimension): serves UC-04,19
    (
        "gold_cognimesh.order_analytics",
        """
        INSERT INTO gold_cognimesh.order_analytics
            (dimension_type, dimension_value, total_revenue,
             revenue_30d, revenue_90d, order_count,
             order_count_30d, avg_order_value, growth_pct)
        SELECT
            'region' AS dimension_type,
            customer_region AS dimension_value,
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
        """,
    ),
    # order_analytics (category dimension): serves UC-10,12
    (
        "gold_cognimesh.order_analytics",
        """
        INSERT INTO gold_cognimesh.order_analytics
            (dimension_type, dimension_value, total_revenue,
             revenue_30d, order_count, order_count_30d,
             avg_order_value, product_count, pct_of_total)
        SELECT
            'category' AS dimension_type,
            product_category AS dimension_value,
            SUM(amount_usd) AS total_revenue,
            COALESCE(SUM(amount_usd)
                FILTER (WHERE created_at > now() - INTERVAL '30 days'), 0
            ) AS revenue_30d,
            COUNT(*) AS order_count,
            COUNT(*) FILTER (
                WHERE created_at > now() - INTERVAL '30 days'
            ) AS order_count_30d,
            ROUND(AVG(amount_usd), 2) AS avg_order_value,
            COUNT(DISTINCT product_id) AS product_count,
            ROUND(
                100.0 * SUM(amount_usd)
                / GREATEST(SUM(SUM(amount_usd)) OVER (), 1), 2
            ) AS pct_of_total
        FROM silver.orders_enriched
        WHERE status IN ('completed', 'pending')
        GROUP BY product_category
        """,
    ),
    # order_analytics (month dimension): serves UC-14
    (
        "gold_cognimesh.order_analytics",
        """
        INSERT INTO gold_cognimesh.order_analytics
            (dimension_type, dimension_value, total_revenue,
             order_count, avg_order_value, unique_customers)
        SELECT
            'month' AS dimension_type,
            DATE_TRUNC('month', created_at)::DATE::TEXT AS dimension_value,
            SUM(amount_usd) AS total_revenue,
            COUNT(*) AS order_count,
            ROUND(AVG(amount_usd), 2) AS avg_order_value,
            COUNT(DISTINCT customer_id) AS unique_customers
        FROM silver.orders_enriched
        WHERE status IN ('completed', 'pending')
        GROUP BY DATE_TRUNC('month', created_at)
        """,
    ),
    # order_analytics (cross_sell dimension): serves UC-18
    (
        "gold_cognimesh.order_analytics",
        """
        INSERT INTO gold_cognimesh.order_analytics
            (dimension_type, dimension_value, dimension_value_2,
             co_purchase_count, co_purchase_pct)
        SELECT
            'cross_sell' AS dimension_type,
            a.product_category AS dimension_value,
            b.product_category AS dimension_value_2,
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
            ) AS co_purchase_pct
        FROM silver.orders_enriched a
        JOIN silver.orders_enriched b
            ON a.customer_id = b.customer_id
            AND a.product_category < b.product_category
            AND b.status IN ('completed', 'pending')
        WHERE a.status IN ('completed', 'pending')
        GROUP BY a.product_category, b.product_category
        """,
    ),
    # customer_orders: serves UC-17
    (
        "gold_cognimesh.customer_orders",
        """
        INSERT INTO gold_cognimesh.customer_orders
            (customer_id, name, region, total_spend, order_count,
             avg_order_value, ltv_segment)
        SELECT
            cp.customer_id, cp.name, cp.region, cp.total_spend,
            cp.total_orders AS order_count,
            CASE
                WHEN cp.total_orders > 0
                    THEN ROUND(cp.total_spend / cp.total_orders, 2)
                ELSE 0
            END AS avg_order_value,
            cp.ltv_segment
        FROM silver.customer_profiles cp
        WHERE cp.ltv_segment IN ('high', 'medium')
        """,
    ),
]


def run_schema(conn: psycopg.Connection) -> None:
    """Execute schema_scale.sql to create all new tables."""
    log.info("Running schema_scale.sql...")
    ddl = SCHEMA_FILE.read_text()
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    log.info("  Schema created.")


def populate_rest_gold(conn: psycopg.Connection) -> float:
    """Populate all 17 REST Gold tables from Silver. Returns elapsed seconds."""
    log.info("Populating REST Gold tables (UC-04 through UC-20)...")
    t0 = time.perf_counter()
    with conn.cursor() as cur:
        for table_name, insert_stmt in _REST_TABLES:
            trunc = pgsql.SQL("TRUNCATE {tbl}").format(
                tbl=_qualified_id(table_name),
            )
            cur.execute(trunc)
            try:
                cur.execute(insert_stmt)
            except Exception as exc:
                log.error("FAILED on %s: %s", table_name, exc)
                raise
    conn.commit()
    elapsed = time.perf_counter() - t0
    log.info("  REST Gold populated in %.2f s", elapsed)
    return elapsed


def populate_cognimesh_gold(conn: psycopg.Connection) -> float:
    """Populate all 4 CogniMesh consolidated Gold tables. Returns elapsed seconds."""
    log.info("Populating CogniMesh consolidated Gold tables...")
    t0 = time.perf_counter()

    # Collect unique table names for truncation (order_analytics has multiple inserts)
    tables_seen: set[str] = set()
    with conn.cursor() as cur:
        for table_name, insert_stmt in _COGNIMESH_TABLES:
            if table_name not in tables_seen:
                trunc = pgsql.SQL("TRUNCATE {tbl} CASCADE").format(
                    tbl=_qualified_id(table_name),
                )
                cur.execute(trunc)
                tables_seen.add(table_name)
            cur.execute(insert_stmt)
    conn.commit()
    elapsed = time.perf_counter() - t0
    log.info("  CogniMesh Gold populated in %.2f s", elapsed)
    return elapsed


def print_row_counts(conn: psycopg.Connection) -> None:
    """Print row counts for all Gold tables in both schemas."""
    log.info("")
    log.info("--- Row Counts ---")

    rest_tables = [t for t, _ in _REST_TABLES]
    # Deduplicate cognimesh tables (order_analytics appears multiple times)
    cognimesh_tables: list[str] = []
    seen: set[str] = set()
    for t, _ in _COGNIMESH_TABLES:
        if t not in seen:
            cognimesh_tables.append(t)
            seen.add(t)

    with conn.cursor() as cur:
        log.info("  [gold_rest]")
        for table_name in rest_tables:
            count_query = pgsql.SQL("SELECT COUNT(*) AS cnt FROM {tbl}").format(
                tbl=_qualified_id(table_name),
            )
            cur.execute(count_query)
            result = cur.fetchone()
            count = result[0] if result else 0
            log.info("    %-45s %s", table_name, f"{count:>8,}")

        log.info("  [gold_cognimesh]")
        for table_name in cognimesh_tables:
            count_query = pgsql.SQL("SELECT COUNT(*) AS cnt FROM {tbl}").format(
                tbl=_qualified_id(table_name),
            )
            cur.execute(count_query)
            result = cur.fetchone()
            count = result[0] if result else 0
            log.info("    %-45s %s", table_name, f"{count:>8,}")


def print_storage_sizes(conn: psycopg.Connection) -> None:
    """Print storage sizes for Gold tables by schema."""
    log.info("")
    log.info("--- Storage Sizes ---")
    with conn.cursor() as cur:
        for schema in ("gold_rest", "gold_cognimesh"):
            cur.execute(
                """
                SELECT
                    schemaname || '.' || tablename AS full_name,
                    pg_total_relation_size(
                        quote_ident(schemaname) || '.' || quote_ident(tablename)
                    ) AS size_bytes
                FROM pg_tables
                WHERE schemaname = %s
                ORDER BY tablename
                """,
                (schema,),
            )
            rows = cur.fetchall()
            total = 0
            log.info("  [%s]", schema)
            for row in rows:
                full_name = row[0]
                size = row[1]
                total += size
                log.info(
                    "    %-45s %s",
                    full_name,
                    _fmt_bytes(size),
                )
            log.info("    %-45s %s", f"TOTAL ({schema})", _fmt_bytes(total))
            log.info("")


def _fmt_bytes(b: int) -> str:
    """Format bytes as human-readable string."""
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b / (1024 * 1024):.1f} MB"


def update_registry_derivation_sql(conn: psycopg.Connection) -> None:
    """Store the real derivation SQL in the UC registry.

    Without this, the registry holds placeholder comments
    ("-- populated by seed_scale.py") which prevents the refresh
    manager from re-deriving Gold tables.
    """
    # Build combined derivation SQL per Gold view
    view_sql: dict[str, str] = {}
    for table_name, insert_stmt in _COGNIMESH_TABLES:
        if table_name in view_sql:
            view_sql[table_name] += "\n;\n" + insert_stmt.strip()
        else:
            view_sql[table_name] = insert_stmt.strip()

    with conn.cursor() as cur:
        for gold_view, derivation_sql in view_sql.items():
            cur.execute(
                "UPDATE cognimesh_internal.uc_registry "  # noqa: S608
                "SET derivation_sql = %(sql)s "
                "WHERE gold_view = %(gv)s AND derivation_sql LIKE '--%%'",
                {"sql": derivation_sql, "gv": gold_view},
            )
    conn.commit()
    log.info("  Updated derivation_sql for %d Gold views in UC registry.", len(view_sql))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
    log.info("Connecting to %s...", DATABASE_URL)
    with psycopg.connect(DATABASE_URL) as conn:
        run_schema(conn)

        rest_time = populate_rest_gold(conn)
        cm_time = populate_cognimesh_gold(conn)
        update_registry_derivation_sql(conn)

        print_row_counts(conn)
        print_storage_sizes(conn)

        log.info("--- Refresh Times ---")
        log.info("  REST Gold (17 tables):          %.2f s", rest_time)
        log.info("  CogniMesh Gold (4 tables):      %.2f s", cm_time)
        log.info("  Ratio (REST / CogniMesh):       %.2fx", rest_time / max(cm_time, 0.001))

    log.info("Seed scale complete!")


if __name__ == "__main__":
    main()
