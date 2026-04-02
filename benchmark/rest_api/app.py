"""FastAPI application for the REST API benchmark (Approach A).

dbt-powered REST with audit logging, lineage (manifest), freshness (run_results),
and capability discovery. Represents a production-grade dbt stack.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI  # type: ignore[import-untyped]

from benchmark.rest_api.database import close_pool, get_connection, get_pool
from benchmark.rest_api.endpoints.at_risk_customers import (
    router as at_risk_router,
)
from benchmark.rest_api.endpoints.customer_details import (
    router as customer_details_router,
)
from benchmark.rest_api.endpoints.customer_health import (
    router as customer_health_router,
)
from benchmark.rest_api.endpoints.customer_lists import (
    router as customer_lists_router,
)
from benchmark.rest_api.endpoints.discover import (
    router as discover_router,
)
from benchmark.rest_api.endpoints.freshness import (
    router as freshness_router,
)
from benchmark.rest_api.endpoints.lineage import (
    router as lineage_router,
)
from benchmark.rest_api.endpoints.orders import (
    router as orders_router,
)
from benchmark.rest_api.endpoints.product_details import (
    router as product_details_router,
)
from benchmark.rest_api.endpoints.revenue import (
    router as revenue_router,
)
from benchmark.rest_api.endpoints.top_products import (
    router as top_products_router,
)
from benchmark.rest_api.middleware import AuditMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage connection pool lifecycle."""
    get_pool()  # eagerly create the pool on startup
    yield
    close_pool()


app = FastAPI(
    title="CogniMesh REST Benchmark (dbt Stack)",
    description=(
        "Approach A — dbt-powered REST with audit, lineage,"
        " freshness, and discovery."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# -- Audit middleware (dbt production stack) -----------------------------------
app.add_middleware(AuditMiddleware, db_get_connection=get_connection)

# -- Routers ------------------------------------------------------------------
# Static-path routers first to avoid /{id} captures
app.include_router(at_risk_router)
app.include_router(customer_lists_router)
app.include_router(customer_health_router)
app.include_router(customer_details_router)
app.include_router(orders_router)
app.include_router(top_products_router)
app.include_router(product_details_router)
app.include_router(revenue_router)
app.include_router(discover_router)
app.include_router(lineage_router)
app.include_router(freshness_router)


# -- Health check -------------------------------------------------------------
@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Basic liveness probe."""
    return {"status": "ok"}
