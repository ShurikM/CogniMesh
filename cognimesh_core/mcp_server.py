"""CogniMesh MCP Server — expose governed data access as MCP tools.

Run with: python -m cognimesh_core.mcp_server
Or configure in Claude Desktop / claude_desktop_config.json
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import mcp.server.stdio  # type: ignore[import-untyped]
from mcp.server import Server  # type: ignore[import-untyped]
from mcp.types import TextContent, Tool  # type: ignore[import-untyped]

from cognimesh_core.approval import ApprovalQueue
from cognimesh_core.audit import AuditLog
from cognimesh_core.capability_index import CapabilityIndex
from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.dependency import DependencyReporter
from cognimesh_core.gateway import Gateway
from cognimesh_core.gold_manager import GoldManager
from cognimesh_core.lineage import LineageTracker
from cognimesh_core.query_composer import TemplateComposer
from cognimesh_core.refresh_manager import RefreshManager
from cognimesh_core.registry import UCRegistry
from cognimesh_core.sqlmesh_adapter import SQLMeshAdapter

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Initialise components (same as FastAPI app lifespan)
# ------------------------------------------------------------------

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
        dbook_bridge.introspect()
    except ImportError:
        logger.info("dbook not installed — running without rich metadata")
    except (OSError, ValueError, RuntimeError):
        logger.warning("dbook initialisation failed", exc_info=True)

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
    if isinstance(gateway.query_composer, TemplateComposer):
        gateway.query_composer.set_rich_metadata(dbook_bridge.get_table_metadata_rich())
        gateway.query_composer.set_concepts(dbook_bridge.get_concepts())
    capability_index.set_concepts(dbook_bridge.get_concepts())

dep_reporter = DependencyReporter(config, lineage_tracker, registry)
refresh_mgr = RefreshManager(config, gold_manager, registry, dbook_bridge=dbook_bridge)

# ------------------------------------------------------------------
# MCP Server
# ------------------------------------------------------------------

server = Server("cognimesh")


def _serialize(obj):
    """JSON-serialize with datetime handling."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return str(obj)


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="cognimesh_query",
            description=(
                "Query the CogniMesh data platform. Routes through "
                "T0 (Gold, sub-10ms), T2 (Silver fallback with dbook "
                "intelligence), or T3 (rejection with explanation). "
                "Every query is audited with lineage and freshness metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural language question about the data",
                    },
                    "uc_id": {
                        "type": "string",
                        "description": "Optional UC ID for direct routing (e.g., 'UC-01')",
                    },
                    "params": {
                        "type": "object",
                        "description": "Query parameters (e.g., {customer_id: '...'})",
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Your agent identifier for access control and audit",
                    },
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="cognimesh_discover",
            description=(
                "Discover available data capabilities. Returns registered "
                "use cases with questions, parameters, freshness guarantees, "
                "and access patterns."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Filter capabilities by agent access permissions",
                    },
                },
            },
        ),
        Tool(
            name="cognimesh_check_drift",
            description=(
                "Check if Silver schema has drifted since last introspection. "
                "Uses dbook SHA256 structural hashing."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="cognimesh_refresh",
            description=(
                "Trigger a scheduled refresh of Gold views. Checks freshness "
                "TTLs and only refreshes stale views. Includes schema drift "
                "detection."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "description": "Force refresh all views regardless of TTL",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="cognimesh_impact_analysis",
            description=(
                "Analyze what Gold views and use cases would be affected "
                "if a Silver table or column changes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "Silver table name (e.g., 'silver.customer_profiles')",
                    },
                    "column": {
                        "type": "string",
                        "description": "Optional column name for column-level impact",
                    },
                },
                "required": ["table"],
            },
        ),
        Tool(
            name="cognimesh_provenance",
            description=(
                "Trace the lineage of a Gold view or column back to its "
                "Silver sources."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "view": {
                        "type": "string",
                        "description": "Gold view name (e.g., 'gold_cognimesh.customer_360')",
                    },
                    "column": {
                        "type": "string",
                        "description": "Optional column name for column-level provenance",
                    },
                },
                "required": ["view"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        if name == "cognimesh_query":
            result = gateway.query(
                question=arguments.get("question", ""),
                uc_id=arguments.get("uc_id"),
                params=arguments.get("params"),
                agent_id=arguments.get("agent_id"),
            )
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result.model_dump(), default=_serialize),
                )
            ]

        elif name == "cognimesh_discover":
            descriptors = capability_index.discover(
                agent_id=arguments.get("agent_id"),
            )
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        [d.model_dump() for d in descriptors],
                        default=_serialize,
                    ),
                )
            ]

        elif name == "cognimesh_check_drift":
            if not dbook_bridge or not dbook_bridge.available:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"available": False, "message": "dbook not enabled"},
                        ),
                    )
                ]
            events = dbook_bridge.check_drift()
            return [
                TextContent(
                    type="text",
                    text=json.dumps({
                        "drift_detected": len(events) > 0,
                        "events": [
                            {
                                "table": e.table_name,
                                "old_hash": e.old_hash[:12],
                                "new_hash": e.new_hash[:12],
                            }
                            for e in events
                        ],
                    }),
                )
            ]

        elif name == "cognimesh_refresh":
            report = refresh_mgr.scheduled_refresh(
                force=arguments.get("force", False),
            )
            return [
                TextContent(
                    type="text",
                    text=json.dumps(report, default=_serialize),
                )
            ]

        elif name == "cognimesh_impact_analysis":
            result = dep_reporter.impact_analysis(
                arguments["table"],
                arguments.get("column"),
            )
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, default=_serialize),
                )
            ]

        elif name == "cognimesh_provenance":
            result = dep_reporter.provenance(
                arguments["view"],
                arguments.get("column"),
            )
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, default=_serialize),
                )
            ]

        else:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name}"}),
                )
            ]

    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": str(e)}),
            )
        ]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
