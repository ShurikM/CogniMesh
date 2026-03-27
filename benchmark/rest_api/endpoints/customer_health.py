"""GET /api/v1/customers/{customer_id}/health — Customer health lookup."""

from __future__ import annotations

from uuid import UUID

import psycopg  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException  # type: ignore[import-untyped]

from benchmark.rest_api.database import get_conn
from benchmark.rest_api.models import CustomerHealthResponse

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


@router.get(
    "/{customer_id}/health",
    response_model=CustomerHealthResponse,
)
def get_customer_health(
    customer_id: UUID,
    conn: psycopg.Connection = Depends(get_conn),
) -> CustomerHealthResponse:
    """Return health status for a single customer.

    No lineage, no audit, no freshness — this is the honest REST baseline.
    """
    row = conn.execute(
        """
        SELECT customer_id, name, region,
               total_orders, total_spend,
               days_since_last_order, ltv_segment,
               health_status
          FROM gold_rest.customer_health
         WHERE customer_id = %s
        """,
        (str(customer_id),),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Customer {customer_id} not found",
        )

    return CustomerHealthResponse(**row)
