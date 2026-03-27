"""Shared fixtures for CogniMesh benchmark tests."""
from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import psycopg  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]
from fastapi.testclient import TestClient  # type: ignore[import-not-found]
from psycopg.rows import dict_row  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# REST API fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def rest_app() -> TestClient:
    """REST API FastAPI TestClient."""
    from benchmark.rest_api.app import app  # type: ignore[import-not-found]

    return TestClient(app)


# ---------------------------------------------------------------------------
# CogniMesh fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mesh_app() -> TestClient:
    """CogniMesh FastAPI TestClient."""
    from benchmark.cognimesh_app.app import app  # type: ignore[import-not-found]

    return TestClient(app)


# ---------------------------------------------------------------------------
# Gateway fixture (for direct Python access, bypassing HTTP)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def gateway() -> Any:
    """CogniMesh Gateway instance for direct testing."""
    from cognimesh_core.audit import AuditLog  # type: ignore[import-not-found]
    from cognimesh_core.capability_index import CapabilityIndex  # type: ignore[import-not-found]
    from cognimesh_core.config import CogniMeshConfig  # type: ignore[import-not-found]
    from cognimesh_core.gateway import Gateway  # type: ignore[import-not-found]
    from cognimesh_core.gold_manager import GoldManager  # type: ignore[import-not-found]
    from cognimesh_core.lineage import LineageTracker  # type: ignore[import-not-found]
    from cognimesh_core.registry import UCRegistry  # type: ignore[import-not-found]

    config = CogniMeshConfig()
    registry = UCRegistry(config)
    cap_index = CapabilityIndex(registry)
    gold_mgr = GoldManager(config)
    lineage = LineageTracker(config)
    audit = AuditLog(config)
    return Gateway(config, registry, cap_index, gold_mgr, lineage, audit)


# ---------------------------------------------------------------------------
# DB fixture for resilience tests that need direct SQL access
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def db_conn() -> Generator[psycopg.Connection[dict[str, Any]], None, None]:
    """Direct Postgres connection for resilience test setup/teardown."""
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://cognimesh:cognimesh@localhost:5432/cognimesh_bench",
    )
    conn = psycopg.connect(url, row_factory=dict_row)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Customer ID fixture -- pick a known customer from the Gold table
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_customer_id(db_conn: psycopg.Connection[dict[str, Any]]) -> str | None:
    """A known customer_id from gold_rest.customer_health."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT customer_id FROM gold_rest.customer_health LIMIT 1")  # noqa: S608
        row = cur.fetchone()
        return str(row["customer_id"]) if row else None
