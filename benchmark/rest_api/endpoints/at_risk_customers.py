"""GET /api/v1/customers/at-risk — At-risk customer list."""

from __future__ import annotations

from decimal import Decimal

import psycopg  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Query  # type: ignore[import-untyped]

from benchmark.rest_api.database import get_conn
from benchmark.rest_api.models import AtRiskCustomerResponse

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


@router.get(
    "/at-risk",
    response_model=list[AtRiskCustomerResponse],
)
def get_at_risk_customers(
    min_risk_score: Decimal = Query(
        default=Decimal("0"), ge=0, description="Minimum risk score filter",
    ),
    limit: int = Query(default=50, ge=1, le=500, description="Max results to return"),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[AtRiskCustomerResponse]:
    """Return at-risk customers filtered by minimum risk score, ordered DESC."""
    rows = conn.execute(
        """
        SELECT customer_id, name, region,
               days_since_last_order, ltv_segment,
               total_spend, risk_score
          FROM gold_rest.at_risk_customers
         WHERE risk_score >= %s
         ORDER BY risk_score DESC
         LIMIT %s
        """,
        (min_risk_score, limit),
    ).fetchall()

    return [AtRiskCustomerResponse(**row) for row in rows]
