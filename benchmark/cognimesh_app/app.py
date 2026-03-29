"""CogniMesh benchmark app — FastAPI wrapper over Gateway."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from cognimesh_core.audit import AuditLog
from cognimesh_core.capability_index import CapabilityIndex
from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.db import close_pool
from cognimesh_core.dependency import DependencyReporter
from cognimesh_core.gateway import Gateway
from cognimesh_core.gold_manager import GoldManager
from cognimesh_core.lineage import LineageTracker
from cognimesh_core.refresh_manager import RefreshManager
from cognimesh_core.registry import UCRegistry
from cognimesh_core.sqlmesh_adapter import SQLMeshAdapter


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str = ""
    uc_id: str | None = None
    params: dict | None = None
    agent_id: str | None = None


# ------------------------------------------------------------------
# Lifespan: initialise gateway components on startup, cleanup on shutdown
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    config = CogniMeshConfig()
    registry = UCRegistry(config)
    capability_index = CapabilityIndex(registry)
    sqlmesh_adapter = SQLMeshAdapter(config)
    gold_manager = GoldManager(config, sqlmesh_adapter=sqlmesh_adapter)
    lineage_tracker = LineageTracker(config)
    audit_log = AuditLog(config)

    gateway = Gateway(
        config=config,
        registry=registry,
        capability_index=capability_index,
        gold_manager=gold_manager,
        lineage_tracker=lineage_tracker,
        audit_log=audit_log,
    )

    dep_reporter = DependencyReporter(config, lineage_tracker, registry)
    refresh_mgr = RefreshManager(config, gold_manager, registry)

    application.state.gateway = gateway
    application.state.capability_index = capability_index
    application.state.dep_reporter = dep_reporter
    application.state.refresh_mgr = refresh_mgr

    yield

    close_pool()


app = FastAPI(title="CogniMesh Benchmark", lifespan=lifespan)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.post("/query")
def query(req: QueryRequest) -> dict[str, Any]:
    """Route a question through the CogniMesh gateway."""
    result = app.state.gateway.query(
        question=req.question,
        uc_id=req.uc_id,
        params=req.params,
        agent_id=req.agent_id,
    )
    return result.model_dump()


@app.get("/discover")
def discover(agent_id: str | None = None) -> list[dict[str, Any]]:
    """Return active UC capabilities for agent discovery.

    If *agent_id* is provided as a query param, only UCs the agent is
    allowed to access are returned.
    """
    descriptors = app.state.capability_index.discover(agent_id=agent_id)
    return [d.model_dump() for d in descriptors]


@app.get("/health")
def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok"}


# ------------------------------------------------------------------
# Dependency endpoints
# ------------------------------------------------------------------

@app.get("/dependencies")
def get_full_graph():
    """Full dependency graph: Silver -> Gold -> UCs."""
    return app.state.dep_reporter.full_graph()


@app.get("/dependencies/impact")
def get_impact(table: str, column: str | None = None):
    """What Gold views/UCs are affected by a change to this Silver table?"""
    return app.state.dep_reporter.impact_analysis(table, column)


@app.get("/dependencies/provenance")
def get_provenance(view: str, column: str | None = None):
    """Where does this Gold column come from?"""
    return app.state.dep_reporter.provenance(view, column)


@app.get("/dependencies/what-if")
def get_what_if(table: str):
    """What would happen if this Silver table changes?"""
    return app.state.dep_reporter.what_if(table)


# ------------------------------------------------------------------
# Refresh endpoints
# ------------------------------------------------------------------

@app.get("/refresh/status")
def get_refresh_status():
    """Current freshness status of all Gold views."""
    return app.state.refresh_mgr.get_refresh_status()


@app.post("/refresh/check")
def check_and_refresh():
    """Check and refresh stale Gold views. Returns what was refreshed."""
    return app.state.refresh_mgr.check_and_refresh_stale()


@app.get("/refresh/plan")
def get_refresh_plan():
    """Preview what would be refreshed without doing it."""
    return app.state.refresh_mgr.get_refresh_plan()
