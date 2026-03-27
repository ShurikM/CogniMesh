"""Resilience scenario: Unsupported UC (question not covered by registered UCs)."""
from __future__ import annotations

from fastapi.testclient import TestClient  # type: ignore[import-not-found]

UNSUPPORTED_QUESTION = "What is the total revenue by region for the last quarter?"


class TestUnsupportedUC:
    """Compare behavior when an unsupported question is asked."""

    def test_rest_unsupported_uc(self, rest_app: TestClient) -> None:
        """REST: No endpoint exists -> 404."""
        r = rest_app.get("/api/v1/revenue/by-region")
        assert r.status_code == 404  # noqa: S101

    def test_cognimesh_unsupported_uc(self, mesh_app: TestClient) -> None:
        """CogniMesh: T2 Silver fallback composes query, or T3 with explanation."""
        r = mesh_app.post("/query", json={"question": UNSUPPORTED_QUESTION})
        assert r.status_code == 200  # noqa: S101
        data = r.json()

        # Should be T2 (composed query served) or T3 (rejected with explanation)
        assert data["tier"] in ("T2", "T3")  # noqa: S101

        if data["tier"] == "T2":
            # T2: CogniMesh composed a query and served data
            assert len(data["data"]) > 0  # noqa: S101
            assert (  # noqa: S101
                data.get("composed_sql")
                or data.get("metadata", {}).get("composed_sql")
            )
        else:
            # T3: Rejected but with structured explanation
            meta = data.get("metadata", {})
            assert "reason" in meta  # noqa: S101
            assert "available_capabilities" in meta  # noqa: S101
