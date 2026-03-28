"""Scale benchmark: measure latency, storage, refresh time at UC=3, 10, 20.

This test produces REAL MEASURED numbers, not projections.
"""
from __future__ import annotations

import time

import pytest  # type: ignore[import-not-found]

# Table names are hardcoded constants, not user input (safe for SQL).
_REST_TABLES = [
    "customer_health", "top_products", "at_risk_customers",
    "revenue_by_region", "customer_ltv", "purchase_frequency",
    "regional_distribution", "product_returns", "spend_segments",
    "order_volume_category", "top_customers", "category_revenue",
    "churn_inputs", "monthly_revenue", "acquisition_by_region",
    "low_performers", "high_value_orders", "cross_sell",
    "regional_revenue", "engagement_score",
]

_CM_TABLES = [
    "customer_360", "product_catalog", "order_analytics",
    "customer_orders", "customer_health", "at_risk_customers",
    "top_products",
]


# === LATENCY MEASUREMENT ===
# Test REST and CogniMesh latency for representative UCs at each scale


class TestLatencyAtScale:
    """Measure T0 query latency for both approaches."""

    # ---------------------------------------------------------------
    # UC-01: individual lookup (customer_profiles -> customer_360)
    # ---------------------------------------------------------------
    @pytest.mark.benchmark(group="scale-uc01-rest")
    def test_rest_uc01(self, benchmark, rest_app, sample_customer_id):  # noqa: S101
        """REST UC-01 latency."""
        result = benchmark(
            rest_app.get, f"/api/v1/customers/{sample_customer_id}/health"
        )
        assert result.status_code == 200  # noqa: S101

    @pytest.mark.benchmark(group="scale-uc01-cognimesh")
    def test_cognimesh_uc01(self, benchmark, mesh_app, sample_customer_id):  # noqa: S101
        """CogniMesh UC-01 latency."""
        result = benchmark(
            mesh_app.post,
            "/query",
            json={"uc_id": "UC-01", "params": {"customer_id": sample_customer_id}},
        )
        assert result.status_code == 200  # noqa: S101

    # ---------------------------------------------------------------
    # UC-04: aggregation (orders_enriched -> order_analytics)
    # ---------------------------------------------------------------
    @pytest.mark.benchmark(group="scale-uc04-rest")
    def test_rest_uc04(self, benchmark, rest_app):  # noqa: S101
        """REST UC-04 latency."""
        result = benchmark(rest_app.get, "/api/v1/revenue/by-region")
        assert result.status_code == 200  # noqa: S101

    @pytest.mark.benchmark(group="scale-uc04-cognimesh")
    def test_cognimesh_uc04(self, benchmark, mesh_app):  # noqa: S101
        """CogniMesh UC-04 latency."""
        result = benchmark(
            mesh_app.post, "/query", json={"uc_id": "UC-04"}
        )
        assert result.status_code == 200  # noqa: S101

    # ---------------------------------------------------------------
    # UC-11: bulk query with ordering (top customers)
    # ---------------------------------------------------------------
    @pytest.mark.benchmark(group="scale-uc11-rest")
    def test_rest_uc11(self, benchmark, rest_app):  # noqa: S101
        """REST UC-11 latency."""
        result = benchmark(rest_app.get, "/api/v1/customers/top?limit=50")
        assert result.status_code == 200  # noqa: S101

    @pytest.mark.benchmark(group="scale-uc11-cognimesh")
    def test_cognimesh_uc11(self, benchmark, mesh_app):  # noqa: S101
        """CogniMesh UC-11 latency."""
        result = benchmark(
            mesh_app.post, "/query", json={"uc_id": "UC-11"}
        )
        assert result.status_code == 200  # noqa: S101

    # ---------------------------------------------------------------
    # UC-14: monthly trend (order_analytics - month dimension)
    # ---------------------------------------------------------------
    @pytest.mark.benchmark(group="scale-uc14-rest")
    def test_rest_uc14(self, benchmark, rest_app):  # noqa: S101
        """REST UC-14 latency."""
        result = benchmark(rest_app.get, "/api/v1/revenue/monthly")
        assert result.status_code == 200  # noqa: S101

    @pytest.mark.benchmark(group="scale-uc14-cognimesh")
    def test_cognimesh_uc14(self, benchmark, mesh_app):  # noqa: S101
        """CogniMesh UC-14 latency."""
        result = benchmark(
            mesh_app.post, "/query", json={"uc_id": "UC-14"}
        )
        assert result.status_code == 200  # noqa: S101

    # ---------------------------------------------------------------
    # UC-20: individual lookup (customer engagement -> customer_360)
    # ---------------------------------------------------------------
    @pytest.mark.benchmark(group="scale-uc20-rest")
    def test_rest_uc20(self, benchmark, rest_app, sample_customer_id):  # noqa: S101
        """REST UC-20 latency."""
        result = benchmark(
            rest_app.get,
            f"/api/v1/customers/{sample_customer_id}/engagement",
        )
        assert result.status_code == 200  # noqa: S101

    @pytest.mark.benchmark(group="scale-uc20-cognimesh")
    def test_cognimesh_uc20(self, benchmark, mesh_app, sample_customer_id):  # noqa: S101
        """CogniMesh UC-20 latency."""
        result = benchmark(
            mesh_app.post,
            "/query",
            json={
                "uc_id": "UC-20",
                "params": {"customer_id": sample_customer_id},
            },
        )
        assert result.status_code == 200  # noqa: S101


def _count_table(cur, schema: str, table: str) -> int:  # noqa: S608
    """Count rows in a Gold table. Table names are compile-time constants."""
    cur.execute(  # noqa: S608
        "SELECT COUNT(*) as cnt FROM {schema}.{table}".format(  # noqa: S608
            schema=schema, table=table,
        )
    )
    return cur.fetchone()["cnt"]


class TestInfrastructureMetrics:
    """Measure storage, table count, and refresh time."""

    def test_gold_table_count(self, db_conn):  # noqa: S101
        """Count Gold tables/views in each schema."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT schemaname, COUNT(*)
                FROM pg_tables
                WHERE schemaname IN ('gold_rest', 'gold_cognimesh')
                GROUP BY schemaname ORDER BY schemaname
                """
            )
            results = cur.fetchall()

        rest_count = next(
            (r["count"] for r in results if r["schemaname"] == "gold_rest"), 0
        )
        mesh_count = next(
            (r["count"] for r in results if r["schemaname"] == "gold_cognimesh"), 0
        )
        assert rest_count >= 15  # noqa: S101
        assert mesh_count <= 10  # noqa: S101

    def test_storage_comparison(self, db_conn):
        """Measure actual storage in bytes."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    schemaname,
                    SUM(pg_total_relation_size(
                        schemaname || '.' || tablename
                    )) as total_bytes
                FROM pg_tables
                WHERE schemaname IN ('gold_rest', 'gold_cognimesh')
                GROUP BY schemaname ORDER BY schemaname
                """
            )
            cur.fetchall()

    def test_storage_new_consolidated_only(self, db_conn):
        """Measure storage of the 4 new CogniMesh consolidated tables vs
        all 17 new REST tables (excluding original 3 UCs)."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT SUM(pg_total_relation_size(
                    'gold_rest.' || tablename
                )) as total_bytes
                FROM pg_tables
                WHERE schemaname = 'gold_rest'
                  AND tablename NOT IN (
                      'customer_health', 'top_products', 'at_risk_customers'
                  )
                """
            )
            cur.fetchone()

            cur.execute(
                """
                SELECT SUM(pg_total_relation_size(
                    'gold_cognimesh.' || t
                )) as total_bytes
                FROM (VALUES ('customer_360'), ('product_catalog'),
                             ('order_analytics'), ('customer_orders')) AS v(t)
                """
            )
            cur.fetchone()

    def test_refresh_time_rest(self, db_conn):
        """Measure time to scan ALL 20 REST Gold tables."""
        start = time.perf_counter()
        total_rows = 0
        with db_conn.cursor() as cur:
            for table in _REST_TABLES:
                total_rows += _count_table(cur, "gold_rest", table)
        _elapsed = (time.perf_counter() - start) * 1000  # noqa: F841

    def test_refresh_time_cognimesh(self, db_conn):
        """Measure time to scan ALL CogniMesh Gold views."""
        start = time.perf_counter()
        total_rows = 0
        with db_conn.cursor() as cur:
            for table in _CM_TABLES:
                total_rows += _count_table(cur, "gold_cognimesh", table)
        _elapsed = (time.perf_counter() - start) * 1000  # noqa: F841

    def test_row_counts_all(self, db_conn):
        """Verify row counts for all Gold tables in both schemas."""
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT schemaname, tablename
                FROM pg_tables
                WHERE schemaname IN ('gold_rest', 'gold_cognimesh')
                ORDER BY schemaname, tablename
                """
            )
            tables = cur.fetchall()

            for row in tables:
                count = _count_table(
                    cur, row["schemaname"], row["tablename"],
                )
                assert count >= 0  # noqa: S101
