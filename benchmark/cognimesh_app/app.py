"""CogniMesh benchmark app — FastAPI wrapper over Gateway."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from cognimesh_core.approval import ApprovalQueue
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

logger = logging.getLogger(__name__)


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
    approval = ApprovalQueue(config)
    registry = UCRegistry(config, approval_queue=approval)
    capability_index = CapabilityIndex(registry)
    sqlmesh_adapter = SQLMeshAdapter(config)
    gold_manager = GoldManager(config, sqlmesh_adapter=sqlmesh_adapter)
    lineage_tracker = LineageTracker(config)
    audit_log = AuditLog(config)

    # dbook integration (optional — graceful fallback if not installed)
    dbook_bridge = None
    if config.dbook_enabled:
        try:
            from cognimesh_core.dbook_bridge import DbookBridge
            dbook_bridge = DbookBridge(config)
            book = dbook_bridge.introspect()
            if book:
                logger.info("dbook: introspected Silver schema (%d tables, %d concepts)",
                           len(dbook_bridge.get_table_metadata_rich()),
                           len(dbook_bridge.get_concepts()))
        except ImportError:
            logger.info("dbook not installed — running without rich metadata")
        except Exception:
            logger.warning("dbook initialization failed", exc_info=True)

    gateway = Gateway(
        config=config,
        registry=registry,
        capability_index=capability_index,
        gold_manager=gold_manager,
        lineage_tracker=lineage_tracker,
        audit_log=audit_log,
        dbook_bridge=dbook_bridge,
    )

    # Inject dbook metadata into composer and capability index
    if dbook_bridge and dbook_bridge.available:
        from cognimesh_core.query_composer import TemplateComposer
        if isinstance(gateway.query_composer, TemplateComposer):
            gateway.query_composer.set_rich_metadata(dbook_bridge.get_table_metadata_rich())
            gateway.query_composer.set_concepts(dbook_bridge.get_concepts())
        capability_index.set_concepts(dbook_bridge.get_concepts())

    dep_reporter = DependencyReporter(config, lineage_tracker, registry)
    refresh_mgr = RefreshManager(config, gold_manager, registry, dbook_bridge=dbook_bridge)

    application.state.gateway = gateway
    application.state.registry = registry
    application.state.approval = approval
    application.state.gold_mgr = gold_manager
    application.state.capability_index = capability_index
    application.state.dep_reporter = dep_reporter
    application.state.refresh_mgr = refresh_mgr
    application.state.dbook_bridge = dbook_bridge

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


@app.post("/refresh/scheduled")
def run_scheduled_refresh(force: bool = False):
    """Run a scheduled refresh cycle. Primary refresh mode.

    Checks all Gold views, refreshes stale ones, returns a detailed report
    with refreshed/skipped/errors lists and timing.
    Call this from cron, Airflow, or manually.
    """
    return app.state.refresh_mgr.scheduled_refresh(force=force)


@app.post("/refresh/check")
def check_and_refresh():
    """Check and refresh stale Gold views. Returns what was refreshed.

    Legacy endpoint — prefer POST /refresh/scheduled for a richer report.
    """
    return app.state.refresh_mgr.check_and_refresh_stale()


@app.get("/refresh/plan")
def get_refresh_plan():
    """Preview what would be refreshed without doing it."""
    return app.state.refresh_mgr.get_refresh_plan()


# ------------------------------------------------------------------
# Schema drift endpoint
# ------------------------------------------------------------------

@app.get("/schema/drift")
def check_schema_drift():
    """Check for Silver schema drift using dbook hash comparison."""
    bridge = app.state.dbook_bridge
    if not bridge or not bridge.available:
        return {"available": False, "message": "dbook not enabled"}
    try:
        events = bridge.check_drift()
        return {
            "drift_detected": len(events) > 0,
            "events": [
                {
                    "table": ev.table_name,
                    "old_hash": ev.old_hash[:12],
                    "new_hash": ev.new_hash[:12],
                    "detected_at": ev.detected_at.isoformat(),
                }
                for ev in events
            ],
        }
    except Exception as e:
        return {"available": True, "error": str(e)}


# ------------------------------------------------------------------
# Approval endpoints
# ------------------------------------------------------------------

@app.get("/approvals")
def list_approvals():
    """List pending approvals."""
    return app.state.approval.list_pending()


@app.get("/approvals/history")
def approval_history(uc_id: str | None = None, limit: int = 50):
    """Get approval history."""
    return app.state.approval.get_history(uc_id=uc_id, limit=limit)


@app.get("/approvals/{approval_id}")
def get_approval(approval_id: int):
    """Get approval details."""
    result = app.state.approval.get(approval_id)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found")
    return result


@app.post("/approvals/{approval_id}/approve")
def approve_uc(approval_id: int, reviewed_by: str = "admin", note: str | None = None):
    """Approve a pending UC change. Triggers Gold derivation."""
    result = app.state.approval.approve(approval_id, reviewed_by=reviewed_by, note=note)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found or already reviewed")

    # Activate the UC
    uc = app.state.registry.activate(result["uc_id"])

    # Trigger Gold derivation if UC has a gold_view
    if uc and uc.gold_view:
        try:
            app.state.gold_mgr.refresh_gold(uc)
        except Exception as e:
            logger.warning("Gold refresh failed after approval: %s", e)

    return {"approval": result, "uc_activated": uc is not None}


@app.post("/approvals/{approval_id}/reject")
def reject_uc(approval_id: int, reviewed_by: str = "admin", reason: str | None = None):
    """Reject a pending UC change."""
    result = app.state.approval.reject(approval_id, reviewed_by=reviewed_by, reason=reason)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found or already reviewed")
    return result
