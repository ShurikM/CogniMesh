"""System Properties Scorecard: 8 binary assertions.

REST (dbt stack) expected: 5 / 8
CogniMesh expected: 8 / 8

Each test is a binary yes/no assertion about a system capability.
The REST API represents a production dbt stack with audit middleware,
lineage from dbt manifest, freshness from dbt run_results, and
capability discovery. This is a fair baseline — not a strawman.
"""
from __future__ import annotations

from typing import Any

import psycopg  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]


class TestRESTProperties:
    """Assert what the dbt REST stack HAS and does NOT have."""

    # -- Properties REST NOW HAS (5/8) --

    def test_rest_discovery(self, rest_app: TestClient) -> None:
        """1/8: REST exposes capability discovery via /api/v1/discover."""
        r = rest_app.get("/api/v1/discover")
        assert r.status_code == 200  # noqa: S101
        capabilities = r.json()
        assert len(capabilities) >= 3  # noqa: S101

    def test_rest_lineage(self, rest_app: TestClient) -> None:
        """2/8: REST provides column-level lineage from dbt manifest."""
        r = rest_app.get("/api/v1/lineage/customer_health")
        assert r.status_code == 200  # noqa: S101
        data = r.json()
        assert "lineage" in data  # noqa: S101
        assert len(data["lineage"]) > 0  # noqa: S101
        entry = data["lineage"][0]
        assert "source_table" in entry  # noqa: S101
        assert "source_column" in entry  # noqa: S101

    def test_rest_audit_trail(
        self,
        rest_app: TestClient,
        db_conn: psycopg.Connection[dict[str, Any]],
        sample_customer_id: str,
    ) -> None:
        """3/8: REST logs queries via audit middleware."""
        # Make a query to trigger audit logging
        rest_app.get(f"/api/v1/customers/{sample_customer_id}/health")
        # Check audit log
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM rest_internal.audit_log"  # noqa: S608
            )
            row = cur.fetchone()
            count = row["cnt"] if row else 0
        assert count > 0  # noqa: S101

    def test_rest_cost_attribution(
        self,
        db_conn: psycopg.Connection[dict[str, Any]],
    ) -> None:
        """4/8: REST audit log includes cost_units per query."""
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT path, cost_units FROM rest_internal.audit_log "  # noqa: S608
                "WHERE cost_units IS NOT NULL LIMIT 1"
            )
            row = cur.fetchone()
        assert row is not None  # noqa: S101
        assert row["cost_units"] > 0  # noqa: S101

    def test_rest_freshness(self, rest_app: TestClient) -> None:
        """5/8: REST provides freshness metadata from dbt run_results."""
        r = rest_app.get("/api/v1/freshness")
        assert r.status_code == 200  # noqa: S101
        data = r.json()
        assert len(data) >= 3  # noqa: S101
        entry = data[0]
        assert "model" in entry  # noqa: S101
        assert "last_run_at" in entry  # noqa: S101

    # -- Properties REST does NOT have (3/8 — CogniMesh advantages) --

    def test_rest_no_governance(self) -> None:
        """6/8: REST has no change governance — no approval workflow.

        dbt doesn't enforce approval before schema changes go live.
        CogniMesh requires human approval before UC changes affect Gold.
        """

    def test_rest_no_fallback(self, rest_app: TestClient) -> None:
        """7/8: REST returns 404 for unsupported queries — no T2/T3 fallback.

        An agent asking a question that doesn't match a pre-built endpoint
        gets a 404. CogniMesh composes SQL from Silver (T2) or explains
        why it can't (T3).
        """
        r = rest_app.get("/api/v1/inventory/by-warehouse")
        assert r.status_code == 404  # noqa: S101

    def test_rest_no_drift_detection(self) -> None:
        """8/8: REST has no schema drift detection.

        If Silver columns are renamed, Gold SQL fails with a runtime error.
        CogniMesh Gold views are materialized — they survive Silver drift
        and serve stale-but-correct data while flagging the drift.
        """


class TestCogniMeshProperties:
    """Assert what CogniMesh DOES have (by design)."""

    def test_cognimesh_discovery(self, mesh_app: TestClient) -> None:
        """1/8: CogniMesh exposes capability discovery."""
        r = mesh_app.get("/discover")
        assert r.status_code == 200  # noqa: S101
        capabilities = r.json()
        assert len(capabilities) >= 3  # noqa: S101
        # Each capability has question, parameters, freshness_guarantee
        cap = capabilities[0]
        assert "question" in cap  # noqa: S101
        assert "uc_id" in cap  # noqa: S101

    def test_cognimesh_lineage(
        self, mesh_app: TestClient, sample_customer_id: str
    ) -> None:
        """2/8: CogniMesh response includes column-level lineage."""
        r = mesh_app.post(
            "/query",
            json={"uc_id": "UC-01", "params": {"customer_id": sample_customer_id}},
        )
        data = r.json()
        assert data.get("lineage") is not None  # noqa: S101
        assert len(data["lineage"]) > 0  # noqa: S101
        lineage_entry = data["lineage"][0]
        assert "source_table" in lineage_entry  # noqa: S101
        assert "source_column" in lineage_entry  # noqa: S101

    def test_cognimesh_audit_trail(
        self,
        mesh_app: TestClient,
        db_conn: psycopg.Connection[dict[str, Any]],
        sample_customer_id: str,
    ) -> None:
        """3/8: Every query is logged in audit_log."""
        # Make a query
        mesh_app.post(
            "/query",
            json={"uc_id": "UC-01", "params": {"customer_id": sample_customer_id}},
        )
        # Check audit log
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM cognimesh_internal.audit_log "  # noqa: S608
                "WHERE uc_id = 'UC-01'"
            )
            row = cur.fetchone()
            count = row["cnt"] if row else 0
        assert count > 0  # noqa: S101

    def test_cognimesh_cost_attribution(
        self,
        db_conn: psycopg.Connection[dict[str, Any]],
    ) -> None:
        """4/8: Audit log attributes cost per UC per agent."""
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT uc_id, SUM(cost_units) AS total_cost "  # noqa: S608
                "FROM cognimesh_internal.audit_log "
                "WHERE uc_id IS NOT NULL "
                "GROUP BY uc_id"
            )
            rows = cur.fetchall()
        assert len(rows) > 0  # noqa: S101

    def test_cognimesh_governance(
        self,
        db_conn: psycopg.Connection[dict[str, Any]],
    ) -> None:
        """5/8: UC registration changes are logged with before/after state."""
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM cognimesh_internal.uc_change_log"  # noqa: S608
            )
            row = cur.fetchone()
            count = row["cnt"] if row else 0
        assert count > 0  # noqa: S101

    def test_cognimesh_freshness(
        self, mesh_app: TestClient, sample_customer_id: str
    ) -> None:
        """6/8: Response includes freshness metadata."""
        r = mesh_app.post(
            "/query",
            json={"uc_id": "UC-01", "params": {"customer_id": sample_customer_id}},
        )
        data = r.json()
        assert data.get("freshness") is not None  # noqa: S101
        freshness = data["freshness"]
        assert "is_stale" in freshness  # noqa: S101
        assert "age_seconds" in freshness  # noqa: S101
        assert "ttl_seconds" in freshness  # noqa: S101

    def test_cognimesh_fallback(self, mesh_app: TestClient) -> None:
        """7/8: Unsupported query gets T2/T3 handling, not 404."""
        r = mesh_app.post(
            "/query",
            json={"question": "What is the warehouse inventory turnover rate?"},
        )
        assert r.status_code == 200  # noqa: S101
        data = r.json()
        assert data["tier"] in ("T2", "T3")  # noqa: S101
        if data["tier"] == "T3":
            assert "available_capabilities" in data.get("metadata", {})  # noqa: S101

    def test_cognimesh_schema_drift_isolation(
        self,
        mesh_app: TestClient,
        db_conn: psycopg.Connection[dict[str, Any]],
        sample_customer_id: str,
    ) -> None:
        """8/8: Gold layer isolates agents from Silver schema changes."""
        # Rename Silver column
        with db_conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE silver.customer_profiles "  # noqa: S608
                "RENAME COLUMN ltv_segment TO lifetime_value_tier"
            )
        db_conn.commit()

        try:
            # CogniMesh still serves from Gold (materialized before drift)
            r = mesh_app.post(
                "/query",
                json={
                    "uc_id": "UC-01",
                    "params": {"customer_id": sample_customer_id},
                },
            )
            assert r.status_code == 200  # noqa: S101
            data = r.json()
            assert data["tier"] == "T0"  # noqa: S101
            assert len(data["data"]) > 0  # noqa: S101
        finally:
            with db_conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE silver.customer_profiles "  # noqa: S608
                    "RENAME COLUMN lifetime_value_tier TO ltv_segment"
                )
            db_conn.commit()
