"""Database connection helper for CogniMesh — psycopg3 with connection pool."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Generator

import psycopg  # type: ignore[import-untyped]
from psycopg.rows import dict_row  # type: ignore[import-untyped]
from psycopg_pool import ConnectionPool  # type: ignore[import-untyped]

from cognimesh_core.config import CogniMeshConfig  # type: ignore[import-untyped]

_pool: ConnectionPool | None = None


def get_pool(config: CogniMeshConfig | None = None) -> ConnectionPool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        cfg = config or CogniMeshConfig()
        _pool = ConnectionPool(
            cfg.database_url,
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row},
        )
    return _pool


@contextmanager
def get_connection(config: CogniMeshConfig | None = None) -> Generator[psycopg.Connection, None, None]:
    """Get a connection from the pool."""
    pool = get_pool(config)
    with pool.connection() as conn:
        yield conn


def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
