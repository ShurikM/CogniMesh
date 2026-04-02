"""Audit and auth middleware for the dbt-powered REST API benchmark.

Represents what a production team adds: request logging and API key auth.
This is the honest baseline — what you'd build in a day with FastAPI middleware.
"""
from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint  # type: ignore[import-untyped]
from starlette.requests import Request  # type: ignore[import-untyped]
from starlette.responses import Response  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Hardcoded API keys for benchmark (in production: secrets manager)
_VALID_API_KEYS = {"benchmark-key-1", "benchmark-key-2", "test-key"}


class AuditMiddleware(BaseHTTPMiddleware):
    """Log every request to rest_internal.audit_log.

    Creates the schema and table on first use.
    """

    def __init__(self, app, db_get_connection=None):
        super().__init__(app)
        self._get_connection = db_get_connection
        self._table_ready = False

    def _ensure_table(self) -> None:
        """Create audit table if not exists."""
        if self._table_ready or not self._get_connection:
            return
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE SCHEMA IF NOT EXISTS rest_internal")
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS rest_internal.audit_log (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMPTZ DEFAULT now(),
                            method TEXT,
                            path TEXT,
                            status_code INTEGER,
                            latency_ms REAL,
                            api_key TEXT,
                            cost_units REAL DEFAULT 1.0
                        )
                    """)
                conn.commit()
            self._table_ready = True
        except Exception as e:
            logger.warning("Failed to create audit table: %s", e)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()

        # Extract API key (optional — don't block if missing for benchmark)
        api_key = request.headers.get("x-api-key", "anonymous")

        response = await call_next(request)

        latency_ms = (time.perf_counter() - start) * 1000

        # Log to audit table (fire-and-forget, don't slow response)
        if self._get_connection and request.url.path.startswith("/api/"):
            try:
                self._ensure_table()
                with self._get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO rest_internal.audit_log "
                            "(method, path, status_code, latency_ms, api_key, cost_units) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (request.method, request.url.path, response.status_code,
                             latency_ms, api_key, 1.0),
                        )
                    conn.commit()
            except Exception as e:
                logger.warning("Audit log failed: %s", e)

        return response
