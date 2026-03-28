"""Order endpoints — UC-10, UC-17."""

from __future__ import annotations

from uuid import UUID

import psycopg  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException  # type: ignore[import-untyped]

from benchmark.rest_api.database import get_conn

router = APIRouter(prefix="/api/v1", tags=["orders"])


@router.get("/orders/volume-by-category")
def get_order_volume_by_category(
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-10: Order volume by product category (last 30 days)."""
    rows = conn.execute(
        """
        SELECT category, order_count_30d, revenue_30d,
               avg_order_value, product_count
          FROM gold_rest.order_volume_category
         ORDER BY revenue_30d DESC
        """,
    ).fetchall()
    return rows


@router.get("/customers/{customer_id}/high-value-orders")
def get_high_value_orders(
    customer_id: UUID,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """UC-17: High-value customer order summary."""
    row = conn.execute(
        """
        SELECT customer_id, name, region, total_spend,
               order_count, avg_order_value, ltv_segment
          FROM gold_rest.high_value_orders
         WHERE customer_id = %s
        """,
        (str(customer_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row
