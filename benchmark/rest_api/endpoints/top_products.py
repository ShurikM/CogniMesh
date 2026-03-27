"""GET /api/v1/products/top — Top products by category."""

from __future__ import annotations

import psycopg  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Query  # type: ignore[import-untyped]

from benchmark.rest_api.database import get_conn
from benchmark.rest_api.models import TopProductResponse

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.get(
    "/top",
    response_model=list[TopProductResponse],
)
def get_top_products(
    category: str | None = Query(default=None, description="Filter by product category"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results to return"),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[TopProductResponse]:
    """Return top products, optionally filtered by category, ordered by rank."""
    if category is not None:
        rows = conn.execute(
            """
            SELECT product_id, category, name, price,
                   units_sold_30d, revenue_30d,
                   return_rate, rank_in_category
              FROM gold_rest.top_products
             WHERE category = %s
             ORDER BY rank_in_category
             LIMIT %s
            """,
            (category, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT product_id, category, name, price,
                   units_sold_30d, revenue_30d,
                   return_rate, rank_in_category
              FROM gold_rest.top_products
             ORDER BY category, rank_in_category
             LIMIT %s
            """,
            (limit,),
        ).fetchall()

    return [TopProductResponse(**row) for row in rows]
