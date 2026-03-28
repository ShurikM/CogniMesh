"""Product endpoints — UC-08, UC-16, UC-18."""

from __future__ import annotations

from uuid import UUID

import psycopg  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, Query  # type: ignore[import-untyped]

from benchmark.rest_api.database import get_conn

router = APIRouter(prefix="/api/v1/products", tags=["products-scale"])


@router.get("/{product_id}/returns")
def get_product_returns(
    product_id: UUID,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """UC-08: Product return analysis."""
    row = conn.execute(
        """
        SELECT product_id, name, category, return_rate,
               units_sold_30d, returns_30d, revenue_impact
          FROM gold_rest.product_returns
         WHERE product_id = %s
        """,
        (str(product_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return row


@router.get("/low-performers")
def get_low_performers(
    limit: int = Query(default=50, ge=1, le=500, description="Max results"),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-16: Low-performing products by performance score."""
    rows = conn.execute(
        """
        SELECT product_id, name, category, revenue_30d,
               units_sold_30d, return_rate, performance_score
          FROM gold_rest.low_performers
         ORDER BY performance_score
         LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return rows


@router.get("/cross-sell")
def get_cross_sell(
    category: str = Query(description="Product category to find cross-sell pairs for"),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-18: Product cross-sell pairs for a category."""
    rows = conn.execute(
        """
        SELECT product_category, co_category,
               co_purchase_count, co_purchase_pct
          FROM gold_rest.cross_sell
         WHERE product_category = %s
         ORDER BY co_purchase_count DESC
        """,
        (category,),
    ).fetchall()
    return rows
