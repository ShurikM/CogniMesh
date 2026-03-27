"""Performance benchmark: T0 latency comparison REST vs CogniMesh."""
from __future__ import annotations

import pytest  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# UC-01: Customer Health — individual lookup
# ---------------------------------------------------------------------------

@pytest.mark.benchmark(group="uc01-customer-health")
def test_rest_uc01_latency(benchmark, rest_app, sample_customer_id):  # noqa: S101
    """REST: GET /api/v1/customers/{id}/health latency."""
    result = benchmark(rest_app.get, f"/api/v1/customers/{sample_customer_id}/health")
    assert result.status_code == 200  # noqa: S101


@pytest.mark.benchmark(group="uc01-customer-health")
def test_cognimesh_uc01_latency(benchmark, mesh_app, sample_customer_id):  # noqa: S101
    """CogniMesh: POST /query UC-01 latency."""
    result = benchmark(
        mesh_app.post,
        "/query",
        json={"uc_id": "UC-01", "params": {"customer_id": sample_customer_id}},
    )
    assert result.status_code == 200  # noqa: S101


# ---------------------------------------------------------------------------
# UC-02: Top Products — bulk query with category filter
# ---------------------------------------------------------------------------

@pytest.mark.benchmark(group="uc02-top-products")
def test_rest_uc02_latency(benchmark, rest_app):  # noqa: S101
    """REST: GET /api/v1/products/top?category=electronics latency."""
    result = benchmark(rest_app.get, "/api/v1/products/top?category=electronics")
    assert result.status_code == 200  # noqa: S101


@pytest.mark.benchmark(group="uc02-top-products")
def test_cognimesh_uc02_latency(benchmark, mesh_app):  # noqa: S101
    """CogniMesh: POST /query UC-02 latency."""
    result = benchmark(
        mesh_app.post,
        "/query",
        json={"uc_id": "UC-02", "params": {"category": "electronics"}},
    )
    assert result.status_code == 200  # noqa: S101


# ---------------------------------------------------------------------------
# UC-03: At-Risk Customers — bulk query ordered by risk_score
# ---------------------------------------------------------------------------

@pytest.mark.benchmark(group="uc03-at-risk-customers")
def test_rest_uc03_latency(benchmark, rest_app):  # noqa: S101
    """REST: GET /api/v1/customers/at-risk latency."""
    result = benchmark(rest_app.get, "/api/v1/customers/at-risk")
    assert result.status_code == 200  # noqa: S101


@pytest.mark.benchmark(group="uc03-at-risk-customers")
def test_cognimesh_uc03_latency(benchmark, mesh_app):  # noqa: S101
    """CogniMesh: POST /query UC-03 latency."""
    result = benchmark(
        mesh_app.post,
        "/query",
        json={"uc_id": "UC-03", "params": {}},
    )
    assert result.status_code == 200  # noqa: S101
