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
from cognimesh_core.gateway import Gateway
from cognimesh_core.gold_manager import GoldManager
from cognimesh_core.lineage import LineageTracker
from cognimesh_core.registry import UCRegistry


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
    gold_manager = GoldManager(config)
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

    application.state.gateway = gateway
    application.state.capability_index = capability_index

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
def discover() -> list[dict[str, Any]]:
    """Return all active UC capabilities for agent discovery."""
    descriptors = app.state.capability_index.discover()
    return [d.model_dump() for d in descriptors]


@app.get("/health")
def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok"}
