"""REST endpoint for UC-04: Revenue by Region."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends  # type: ignore[import-not-found]

from benchmark.rest_api.database import get_conn  # type: ignore[import-not-found]
from benchmark.uc04.rest_changes.models_uc04 import RevenueByRegionResponse  # type: ignore[import-not-found]

router = APIRouter()


@router.get(
    "/api/v1/revenue/by-region",
    response_model=list[RevenueByRegionResponse],
)
def get_revenue_by_region(
    region: str | None = None,
    conn: Any = Depends(get_conn),
) -> list[RevenueByRegionResponse]:
    """Return revenue aggregated by region for the last 30 days."""
    with conn.cursor() as cur:
        if region:
            cur.execute(
                "SELECT region, total_revenue, order_count, avg_order_value "
                "FROM gold_rest.revenue_by_region WHERE region = %s",
                (region,),
            )
        else:
            cur.execute(
                "SELECT region, total_revenue, order_count, avg_order_value "  # noqa: S608
                "FROM gold_rest.revenue_by_region ORDER BY total_revenue DESC",
            )
        rows = cur.fetchall()
    return [RevenueByRegionResponse(**row) for row in rows]
