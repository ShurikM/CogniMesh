"""Tests for UC-04 REST endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient  # type: ignore[import-not-found]

from benchmark.rest_api.app import app  # type: ignore[import-not-found]

client = TestClient(app)


def test_revenue_by_region_all() -> None:
    """GET /api/v1/revenue/by-region returns revenue data for all regions."""
    r = client.get("/api/v1/revenue/by-region")
    assert r.status_code == 200  # noqa: S101
    data = r.json()
    assert len(data) > 0  # noqa: S101


def test_revenue_by_region_filtered() -> None:
    """GET /api/v1/revenue/by-region?region=NA returns single region."""
    r = client.get("/api/v1/revenue/by-region?region=NA")
    assert r.status_code == 200  # noqa: S101
