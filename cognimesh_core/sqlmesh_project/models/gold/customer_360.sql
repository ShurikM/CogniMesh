MODEL (
  name gold_cognimesh.customer_360,
  kind FULL,
  grain customer_id,
  description 'Consolidated customer view serving 10 UCs'
);

SELECT
    cp.customer_id,
    cp.name,
    cp.email,
    cp.region,
    cp.signup_date,
    cp.total_orders,
    cp.total_spend,
    cp.days_since_last_order,
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
