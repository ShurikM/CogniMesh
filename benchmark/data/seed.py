"""
CogniMesh Benchmark: Seed Data Generator

Generates deterministic e-commerce data in Postgres.
Run: uv run python benchmark/data/seed.py
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg  # type: ignore[import-untyped]
from faker import Faker  # type: ignore[import-untyped]

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://cognimesh:cognimesh@localhost:5432/cognimesh_bench",
)

SEED = 42
NUM_CUSTOMERS = 10_000
NUM_PRODUCTS = 500
NUM_ORDERS = 200_000

REGIONS = ["NA", "EMEA", "APAC", "LATAM", "MEA"]
CATEGORIES = [
    "electronics", "clothing", "home", "sports",
    "books", "food", "toys", "beauty",
]
STATUSES = [
    "completed", "completed", "completed", "completed",
    "pending", "refunded", "cancelled",
]  # 57% completed

log = logging.getLogger(__name__)

fake = Faker()
Faker.seed(SEED)

_rng = __import__("random")
_rng.seed(SEED)


def generate_customers() -> list[tuple]:
    rows = []
    for _ in range(NUM_CUSTOMERS):
        rows.append((
            str(uuid.uuid4()),
            fake.name(),
            fake.email(),
            fake.date_between(
                start_date="-5y", end_date="-30d"
            ),
            _rng.choice(REGIONS),
        ))
    return rows


def generate_products() -> list[tuple]:
    rows = []
    for _ in range(NUM_PRODUCTS):
        rows.append((
            str(uuid.uuid4()),
            fake.catch_phrase(),
            _rng.choice(CATEGORIES),
            round(_rng.uniform(5.0, 500.0), 2),
            str(uuid.uuid4()),
        ))
    return rows


def generate_orders(
    customer_ids: list[str],
    product_ids: list[str],
) -> list[tuple]:
    rows = []
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=365)
    for _ in range(NUM_ORDERS):
        created = start + timedelta(
            seconds=_rng.randint(0, 365 * 86400)
        )
        rows.append((
            str(uuid.uuid4()),
            _rng.choice(customer_ids),
            _rng.choice(product_ids),
            round(_rng.uniform(10.0, 1000.0), 2),
            _rng.choice(STATUSES),
            created,
        ))
    return rows


def seed_bronze(
    conn: psycopg.Connection,
) -> tuple[list[str], list[str]]:
    log.info("Seeding bronze.customers...")
    customers = generate_customers()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE bronze.customers CASCADE")
        with cur.copy(
            "COPY bronze.customers "
            "(customer_id, name, email, signup_date, region) "
            "FROM STDIN"
        ) as copy:
            for row in customers:
                copy.write_row(row)

    customer_ids = [c[0] for c in customers]

    log.info("Seeding bronze.products...")
    products = generate_products()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE bronze.products CASCADE")
        with cur.copy(
            "COPY bronze.products "
            "(product_id, name, category, price, supplier_id) "
            "FROM STDIN"
        ) as copy:
            for row in products:
                copy.write_row(row)

    product_ids = [p[0] for p in products]

    log.info("Seeding bronze.orders...")
    orders = generate_orders(customer_ids, product_ids)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE bronze.orders CASCADE")
        with cur.copy(
            "COPY bronze.orders "
            "(order_id, customer_id, product_id, "
            "amount, status, created_at) "
            "FROM STDIN"
        ) as copy:
            for row in orders:
                copy.write_row(row)

    conn.commit()
    log.info(
        "  Bronze: %d customers, %d products, %d orders",
        NUM_CUSTOMERS, NUM_PRODUCTS, NUM_ORDERS,
    )
    return customer_ids, product_ids


def derive_silver(conn: psycopg.Connection) -> None:
    log.info("Deriving silver layer...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE silver.customer_profiles")
        cur.execute("""
            INSERT INTO silver.customer_profiles
                (customer_id, name, email, region, signup_date,
                 total_orders, total_spend,
                 days_since_last_order, ltv_segment)
            SELECT
                c.customer_id, c.name, c.email,
                c.region, c.signup_date,
                COALESCE(agg.total_orders, 0),
                COALESCE(agg.total_spend, 0),
                COALESCE(
                    EXTRACT(DAY FROM now() - agg.last_order_date
                    )::INTEGER, 9999),
                CASE
                    WHEN COALESCE(agg.total_spend, 0) > 5000
                        THEN 'high'
                    WHEN COALESCE(agg.total_spend, 0) > 1000
                        THEN 'medium'
                    ELSE 'low'
                END
            FROM bronze.customers c
            LEFT JOIN (
                SELECT
                    customer_id,
                    COUNT(*) AS total_orders,
                    SUM(amount) AS total_spend,
                    MAX(created_at) AS last_order_date
                FROM bronze.orders
                WHERE status IN ('completed', 'pending')
                GROUP BY customer_id
            ) agg ON c.customer_id = agg.customer_id
        """)

        cur.execute("TRUNCATE silver.product_metrics")
        cur.execute("""
            INSERT INTO silver.product_metrics
                (product_id, name, category, price,
                 units_sold_30d, revenue_30d,
                 return_rate, stock_status)
            SELECT
                p.product_id, p.name, p.category, p.price,
                COALESCE(recent.units, 0),
                COALESCE(recent.revenue, 0),
                COALESCE(returns.rate, 0),
                CASE
                    WHEN COALESCE(recent.units, 0) > 50
                        THEN 'low_stock'
                    WHEN COALESCE(recent.units, 0) > 100
                        THEN 'out_of_stock'
                    ELSE 'in_stock'
                END
            FROM bronze.products p
            LEFT JOIN (
                SELECT product_id,
                    COUNT(*) AS units,
                    SUM(amount) AS revenue
                FROM bronze.orders
                WHERE created_at > now() - INTERVAL '30 days'
                  AND status = 'completed'
                GROUP BY product_id
            ) recent ON p.product_id = recent.product_id
            LEFT JOIN (
                SELECT product_id,
                    COUNT(*) FILTER (
                        WHERE status = 'refunded'
                    )::NUMERIC
                    / NULLIF(COUNT(*), 0) AS rate
                FROM bronze.orders
                GROUP BY product_id
            ) returns ON p.product_id = returns.product_id
        """)

        cur.execute("TRUNCATE silver.orders_enriched")
        cur.execute("""
            INSERT INTO silver.orders_enriched
                (order_id, customer_id, product_id,
                 customer_region, product_category,
                 amount_usd, status, created_at)
            SELECT
                o.order_id, o.customer_id, o.product_id,
                c.region, p.category,
                o.amount, o.status, o.created_at
            FROM bronze.orders o
            JOIN bronze.customers c
                ON o.customer_id = c.customer_id
            JOIN bronze.products p
                ON o.product_id = p.product_id
        """)

    conn.commit()
    log.info("  Silver layer derived from Bronze")


# -- Gold layer SQL templates -----------------------------------------
# The {schema} placeholder is a trusted internal value (gold_rest or
# gold_cognimesh), never user input, so string formatting is safe here.

_GOLD_CUSTOMER_HEALTH = """
    INSERT INTO {schema}.customer_health
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
    FROM silver.customer_profiles
"""

_GOLD_TOP_PRODUCTS = """
    INSERT INTO {schema}.top_products
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
    FROM silver.product_metrics
"""

_GOLD_AT_RISK = """
    INSERT INTO {schema}.at_risk_customers
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
           AND days_since_last_order > 30)
"""

_GOLD_TRUNCATE_TABLES = [
    "customer_health",
    "top_products",
    "at_risk_customers",
]

_GOLD_INSERT_TEMPLATES = [
    _GOLD_CUSTOMER_HEALTH,
    _GOLD_TOP_PRODUCTS,
    _GOLD_AT_RISK,
]


def populate_gold(
    conn: psycopg.Connection, schema: str,
) -> None:
    log.info("Populating %s gold tables...", schema)
    with conn.cursor() as cur:
        for table, template in zip(
            _GOLD_TRUNCATE_TABLES, _GOLD_INSERT_TEMPLATES
        ):
            cur.execute(
                "TRUNCATE " + schema + "." + table
            )
            cur.execute(template.format(schema=schema))
    conn.commit()
    log.info("  %s gold tables populated", schema)


_STAT_TABLES = [
    "bronze.customers",
    "bronze.products",
    "bronze.orders",
    "silver.customer_profiles",
    "silver.product_metrics",
    "silver.orders_enriched",
    "gold_rest.customer_health",
    "gold_rest.top_products",
    "gold_rest.at_risk_customers",
    "gold_cognimesh.customer_health",
    "gold_cognimesh.top_products",
    "gold_cognimesh.at_risk_customers",
]


def print_stats(conn: psycopg.Connection) -> None:
    log.info("--- Row Counts ---")
    with conn.cursor() as cur:
        for table in _STAT_TABLES:
            # table names are hard-coded constants above
            sql = "SELECT COUNT(*) FROM " + table  # noqa: S608
            cur.execute(sql)
            result = cur.fetchone()
            count = result[0] if result else 0
            log.info("  %s: %s", table, f"{count:,}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
    log.info("Connecting to %s...", DATABASE_URL)
    with psycopg.connect(DATABASE_URL) as conn:
        _customer_ids, _product_ids = seed_bronze(conn)
        derive_silver(conn)
        populate_gold(conn, "gold_rest")
        populate_gold(conn, "gold_cognimesh")
        print_stats(conn)
    log.info("Seed complete!")


if __name__ == "__main__":
    main()
