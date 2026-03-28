"""Customer list/aggregation endpoints — UC-07, UC-11, UC-15."""

from __future__ import annotations

import psycopg  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Query  # type: ignore[import-untyped]

from benchmark.rest_api.database import get_conn

router = APIRouter(prefix="/api/v1", tags=["customer-lists"])


@router.get("/distribution/by-region")
def get_regional_distribution(
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-07: Regional customer distribution."""
    rows = conn.execute(
        """
        SELECT region, customer_count, avg_spend,
               avg_orders, pct_high_ltv
          FROM gold_rest.regional_distribution
         ORDER BY customer_count DESC
        """,
    ).fetchall()
    return rows


@router.get("/customers/top")
def get_top_customers(
    limit: int = Query(default=50, ge=1, le=500, description="Max results"),
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-11: Top customers by spend."""
    rows = conn.execute(
        """
        SELECT customer_id, name, region, total_spend,
               total_orders, ltv_segment, rank_overall
          FROM gold_rest.top_customers
         ORDER BY rank_overall
         LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return rows


@router.get("/acquisition/by-region")
def get_acquisition_by_region(
    conn: psycopg.Connection = Depends(get_conn),
) -> list[dict]:
    """UC-15: Customer acquisition by region and month."""
    rows = conn.execute(
        """
        SELECT region, signup_month, new_customers
          FROM gold_rest.acquisition_by_region
         ORDER BY signup_month DESC, region
        """,
    ).fetchall()
    return rows
