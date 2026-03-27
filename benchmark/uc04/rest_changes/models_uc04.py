"""Response model for UC-04: Revenue by Region."""

from decimal import Decimal

from pydantic import BaseModel  # type: ignore[import-not-found]


class RevenueByRegionResponse(BaseModel):
    region: str
    total_revenue: Decimal
    order_count: int
    avg_order_value: Decimal
