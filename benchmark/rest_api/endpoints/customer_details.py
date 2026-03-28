"""Customer detail endpoints — UC-05, UC-06, UC-09, UC-13, UC-20."""

from __future__ import annotations

from uuid import UUID

import psycopg  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException  # type: ignore[import-untyped]

from benchmark.rest_api.database import get_conn

router = APIRouter(prefix="/api/v1/customers", tags=["customer-details"])


@router.get("/{customer_id}/ltv")
def get_customer_ltv(
    customer_id: UUID,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """UC-05: Customer lifetime value."""
    row = conn.execute(
        """
        SELECT customer_id, name, region, signup_date,
               total_orders, total_spend, ltv_segment,
               months_active, avg_monthly_spend
          FROM gold_rest.customer_ltv
         WHERE customer_id = %s
        """,
        (str(customer_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row


@router.get("/{customer_id}/frequency")
def get_customer_frequency(
    customer_id: UUID,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """UC-06: Purchase frequency for a customer."""
    row = conn.execute(
        """
        SELECT customer_id, name, total_orders,
               days_since_last_order, avg_days_between_orders,
               frequency_segment
          FROM gold_rest.purchase_frequency
         WHERE customer_id = %s
        """,
        (str(customer_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row


@router.get("/{customer_id}/spend-segment")
def get_customer_spend_segment(
    customer_id: UUID,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """UC-09: Customer spend segmentation."""
    row = conn.execute(
        """
        SELECT customer_id, name, region, total_spend,
               spend_segment, percentile
          FROM gold_rest.spend_segments
         WHERE customer_id = %s
        """,
        (str(customer_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row


@router.get("/{customer_id}/churn-inputs")
def get_customer_churn_inputs(
    customer_id: UUID,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """UC-13: Churn prediction inputs for a customer."""
    row = conn.execute(
        """
        SELECT customer_id, name, days_since_last_order,
               total_orders, total_spend, ltv_segment,
               region, churn_risk_score
          FROM gold_rest.churn_inputs
         WHERE customer_id = %s
        """,
        (str(customer_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row


@router.get("/{customer_id}/engagement")
def get_customer_engagement(
    customer_id: UUID,
    conn: psycopg.Connection = Depends(get_conn),
) -> dict:
    """UC-20: Customer engagement score."""
    row = conn.execute(
        """
        SELECT customer_id, name, region, total_orders,
               days_since_last_order, total_spend,
               engagement_score, engagement_tier
          FROM gold_rest.engagement_score
         WHERE customer_id = %s
        """,
        (str(customer_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row
