"""FastAPI application for the REST API benchmark (Approach A).

Traditional REST with dedicated Gold tables.
No lineage, no audit, no freshness, no discovery — by architectural design.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI  # type: ignore[import-untyped]

from benchmark.rest_api.database import close_pool, get_pool
from benchmark.rest_api.endpoints.at_risk_customers import (
    router as at_risk_router,
)
from benchmark.rest_api.endpoints.customer_health import (
    router as customer_health_router,
)
from benchmark.rest_api.endpoints.top_products import (
    router as top_products_router,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage connection pool lifecycle."""
    get_pool()  # eagerly create the pool on startup
    yield
    close_pool()


app = FastAPI(
    title="CogniMesh REST Benchmark",
    description="Approach A — traditional REST with dedicated Gold tables.",
    version="0.1.0",
    lifespan=lifespan,
)

# -- Routers ------------------------------------------------------------------
app.include_router(at_risk_router)  # before customer_health to avoid /{id} capturing "at-risk"
app.include_router(customer_health_router)
app.include_router(top_products_router)


# -- Health check -------------------------------------------------------------
@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Basic liveness probe."""
    return {"status": "ok"}
