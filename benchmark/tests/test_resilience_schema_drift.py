"""Resilience scenario: Silver schema drift (column rename)."""
from __future__ import annotations

from typing import Any

import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]

# Exact Gold derivation SQL from benchmark/rest_api/gold_tables.sql
# Used to attempt re-deriving Gold after Silver column rename.
_GOLD_REST_CUSTOMER_HEALTH_SQL = """\
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
FROM silver.customer_profiles
"""


class TestSchemaDrift:
    """Rename a Silver column and observe behavior of both approaches."""

    def test_rest_schema_drift(
        self,
        rest_app: TestClient,
        db_conn: psycopg.Connection[dict[str, Any]],
        sample_customer_id: str,
    ) -> None:
        """REST: Gold derivation SQL references old column -> refresh fails after drift."""
        # 1. Verify works before drift
        r = rest_app.get(f"/api/v1/customers/{sample_customer_id}/health")
        assert r.status_code == 200  # noqa: S101

        # 2. Simulate drift: rename column in Silver
        with db_conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE silver.customer_profiles "  # noqa: S608
                "RENAME COLUMN ltv_segment TO lifetime_value_tier"
            )
        db_conn.commit()

        try:
            # 3. Attempt Gold refresh — SQL references old column name
            with db_conn.cursor() as cur:
                cur.execute("TRUNCATE gold_rest.customer_health")  # noqa: S608
                try:
                    cur.execute(_GOLD_REST_CUSTOMER_HEALTH_SQL)  # noqa: S608
                    db_conn.commit()
                    # If somehow succeeds the data would reference the wrong column
                    pytest.fail(  # pragma: no cover
                        "Expected SQL error because ltv_segment was renamed"
                    )
                except Exception as exc:
                    db_conn.rollback()
                    # EXPECTED: SQL error because ltv_segment no longer exists
                    error_text = str(exc).lower()
                    assert (  # noqa: S101
                        "ltv_segment" in error_text or "column" in error_text
                    ), f"Unexpected error: {exc}"
        finally:
            # 4. Teardown: rename back and re-populate Gold
            with db_conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE silver.customer_profiles "  # noqa: S608
                    "RENAME COLUMN lifetime_value_tier TO ltv_segment"
                )
            db_conn.commit()
            # Re-populate Gold from Silver
            with db_conn.cursor() as cur:
                cur.execute("TRUNCATE gold_rest.customer_health")  # noqa: S608
                cur.execute(_GOLD_REST_CUSTOMER_HEALTH_SQL)  # noqa: S608
            db_conn.commit()

    def test_cognimesh_schema_drift(
        self,
        mesh_app: TestClient,
        db_conn: psycopg.Connection[dict[str, Any]],
        sample_customer_id: str,
    ) -> None:
        """CogniMesh: Gold is an isolation layer. Serves stale data, detects drift."""
        # 1. Verify works before drift
        r = mesh_app.post(
            "/query",
            json={"uc_id": "UC-01", "params": {"customer_id": sample_customer_id}},
        )
        assert r.status_code == 200  # noqa: S101
        data = r.json()
        assert data["tier"] == "T0"  # noqa: S101

        # 2. Simulate drift
        with db_conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE silver.customer_profiles "  # noqa: S608
                "RENAME COLUMN ltv_segment TO lifetime_value_tier"
            )
        db_conn.commit()

        try:
            # 3. Query CogniMesh — Gold view still has data from before drift
            r = mesh_app.post(
                "/query",
                json={"uc_id": "UC-01", "params": {"customer_id": sample_customer_id}},
            )
            assert r.status_code == 200  # noqa: S101
            data = r.json()
            # CogniMesh continues serving from Gold (isolation layer)
            assert data["tier"] == "T0"  # noqa: S101
            assert len(data["data"]) > 0  # noqa: S101
        finally:
            # Teardown: rename column back
            with db_conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE silver.customer_profiles "  # noqa: S608
                    "RENAME COLUMN lifetime_value_tier TO ltv_segment"
                )
            db_conn.commit()
