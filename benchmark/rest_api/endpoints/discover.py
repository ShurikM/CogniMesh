"""GET /api/v1/discover — Capability discovery for the dbt REST API."""
from __future__ import annotations

from fastapi import APIRouter  # type: ignore[import-untyped]

router = APIRouter(prefix="/api/v1", tags=["discovery"])

_CAPABILITIES = [
    {
        "endpoint": "/api/v1/customers/{id}/health",
        "method": "GET",
        "description": "Customer health status lookup",
        "model": "customer_health",
        "access_pattern": "individual_lookup",
    },
    {
        "endpoint": "/api/v1/products/top",
        "method": "GET",
        "description": "Top products by revenue",
        "model": "top_products",
        "access_pattern": "bulk_query",
    },
    {
        "endpoint": "/api/v1/customers/at-risk",
        "method": "GET",
        "description": "At-risk customers list",
        "model": "at_risk_customers",
        "access_pattern": "bulk_query",
    },
    {
        "endpoint": "/api/v1/lineage/{model}",
        "method": "GET",
        "description": "Column-level lineage from dbt manifest",
        "model": None,
        "access_pattern": "metadata",
    },
    {
        "endpoint": "/api/v1/freshness",
        "method": "GET",
        "description": "Model freshness from dbt run results",
        "model": None,
        "access_pattern": "metadata",
    },
]


@router.get("/discover")
def discover() -> list[dict]:
    """Return available API capabilities."""
    return _CAPABILITIES
