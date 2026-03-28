"""Revenue endpoints — UC-04, UC-12, UC-14, UC-19."""

from __future__ import annotations

import psycopg  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends  # type: ignore[import-untyped]

from benchmark.rest_api.database import get_conn

router = APIRouter(prefix="/api/v1/revenue", tags=["revenue"])


@router.get("/by-region")
def get_revenue_by_region(
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-04: Revenue breakdown by region."""
    rows = conn.execute(
        """
        SELECT region, total_revenue, order_count, avg_order_value
          FROM gold_rest.revenue_by_region
         ORDER BY total_revenue DESC
        """,
    ).fetchall()
    return rows


@router.get("/by-category")
def get_revenue_by_category(
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-12: Category revenue share."""
    rows = conn.execute(
        """
        SELECT category, total_revenue, pct_of_total, order_count
          FROM gold_rest.category_revenue
         ORDER BY total_revenue DESC
        """,
    ).fetchall()
    return rows


@router.get("/monthly")
def get_monthly_revenue(
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-14: Monthly revenue trend."""
    rows = conn.execute(
        """
        SELECT month, total_revenue, order_count,
               unique_customers, avg_order_value
          FROM gold_rest.monthly_revenue
         ORDER BY month DESC
        """,
    ).fetchall()
    return rows


@router.get("/regional-comparison")
def get_regional_revenue_comparison(
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-19: Regional revenue comparison (30d vs 90d)."""
    rows = conn.execute(
        """
        SELECT region, revenue_30d, revenue_90d,
               growth_pct, order_count_30d
          FROM gold_rest.regional_revenue
         ORDER BY revenue_30d DESC
        """,
    ).fetchall()
    return rows
