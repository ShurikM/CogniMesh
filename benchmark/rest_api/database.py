"""Postgres connection pool for the REST API benchmark — psycopg3 + psycopg_pool."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg  # type: ignore[import-untyped]
from psycopg.rows import dict_row  # type: ignore[import-untyped]
from psycopg_pool import ConnectionPool  # type: ignore[import-untyped]

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://cognimesh:cognimesh@localhost:5432/cognimesh_bench",
)

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Get or create the connection pool (singleton)."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row},
        )
    return _pool


def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_connection() -> Generator[psycopg.Connection[dict[str, Any]], None, None]:
    """Get a connection from the pool (context-manager)."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def get_conn() -> Generator[psycopg.Connection[dict[str, Any]], None, None]:
    """FastAPI dependency — yields a connection then returns it to the pool."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn
