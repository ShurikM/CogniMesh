"""Pydantic v2 response models for REST API benchmark endpoints."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel  # type: ignore[import-untyped]


class CustomerHealthResponse(BaseModel):
    """Customer health status — derived from gold_rest.customer_health."""

    customer_id: UUID
    name: str
    region: str
    total_orders: int
    total_spend: Decimal
    days_since_last_order: int
    ltv_segment: str
    health_status: str


class TopProductResponse(BaseModel):
    """Top product in a category — derived from gold_rest.top_products."""

    product_id: UUID
    category: str
    name: str
    price: Decimal
    units_sold_30d: int
    revenue_30d: Decimal
    return_rate: Decimal
    rank_in_category: int


class AtRiskCustomerResponse(BaseModel):
    """At-risk customer — derived from gold_rest.at_risk_customers."""

    customer_id: UUID
    name: str
    region: str
    days_since_last_order: int
    ltv_segment: str
    total_spend: Decimal
    risk_score: Decimal
