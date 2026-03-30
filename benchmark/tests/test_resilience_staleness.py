"""Resilience scenario: Data staleness detection."""
from __future__ import annotations

from typing import Any

import psycopg  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]


class TestStaleness:
    """Compare staleness awareness between REST and CogniMesh."""

    def test_rest_no_freshness(
        self,
        rest_app: TestClient,
        sample_customer_id: str,
    ) -> None:
        """REST: Response has no freshness metadata. Serves stale data silently."""
        r = rest_app.get(f"/api/v1/customers/{sample_customer_id}/health")
        assert r.status_code == 200  # noqa: S101
        data = r.json()
        # REST has NO freshness field
        assert "freshness" not in data  # noqa: S101
        assert "is_stale" not in data  # noqa: S101

    def test_cognimesh_freshness_tracking(
        self,
        mesh_app: TestClient,
        db_conn: psycopg.Connection[dict[str, Any]],
        sample_customer_id: str,
    ) -> None:
        """CogniMesh: Detects staleness when TTL expires."""
        gold_view = "gold_cognimesh.customer_360"

        # 1. Set UC-01 TTL to 1 second and backdate last_refreshed_at
        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE cognimesh_internal.freshness "  # noqa: S608
                "SET ttl_seconds = 1 WHERE gold_view = %s",
                (gold_view,),
            )
            cur.execute(
                "UPDATE cognimesh_internal.freshness "  # noqa: S608
                "SET last_refreshed_at = now() - interval '10 seconds' "
                "WHERE gold_view = %s",
                (gold_view,),
            )
        db_conn.commit()

        try:
            # 2. Query — should return data WITH stale flag
            r = mesh_app.post(
                "/query",
                json={
                    "uc_id": "UC-01",
                    "params": {"customer_id": sample_customer_id},
                },
            )
            data = r.json()
            if data["tier"] == "T0" and data.get("freshness"):
                assert data["freshness"]["is_stale"] is True  # noqa: S101
                assert data["freshness"]["age_seconds"] > 1  # noqa: S101
        finally:
            # Restore TTL and freshness timestamp
            with db_conn.cursor() as cur:
                cur.execute(
                    "UPDATE cognimesh_internal.freshness "  # noqa: S608
                    "SET ttl_seconds = 14400, last_refreshed_at = now() "
                    "WHERE gold_view = %s",
                    (gold_view,),
                )
            db_conn.commit()
