"""CogniMesh core data models — Pydantic v2."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field  # type: ignore[import-untyped]


class UseCase(BaseModel):
    """A registered Use Case — the authoring unit is a question, not a table."""

    id: str
    question: str
    consuming_agent: str | None = None
    required_fields: list[str]
    access_pattern: Literal["individual_lookup", "bulk_query", "aggregation"]
    freshness_ttl_seconds: int
    gold_view: str | None = None
    gold_schema: str = "gold_cognimesh"
    source_tables: list[str] | None = None
    derivation_sql: str | None = None
    status: Literal["active", "pending", "deprecated"] = "active"
    allowed_agents: list[str] | None = None  # None = open access (all agents allowed)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ColumnInfo(BaseModel):
    """Metadata about a single column in a Gold view."""

    name: str
    type: str
    source_table: str
    source_column: str
    transformation: str | None = None  # direct, aggregation:sum, filter, join, computed


class GoldViewMeta(BaseModel):
    """Metadata about a materialized Gold view."""

    view_name: str
    derived_from_ucs: list[str]
    source_tables: list[str]
    last_refreshed_at: datetime | None = None
    freshness_ttl_seconds: int = 0
    columns: list[ColumnInfo] = []
    row_count: int = 0


class ColumnLineage(BaseModel):
    """Column-level lineage: traces a Gold column to its Silver/Bronze source."""

    gold_column: str
    source_table: str
    source_column: str
    transformation: str | None = None
    model_version: str | None = None


class FreshnessInfo(BaseModel):
    """Freshness status for a Gold view."""

    gold_view: str
    last_refreshed_at: datetime | None = None
    ttl_seconds: int = 0
    age_seconds: float = 0
    is_stale: bool = False


class AuditEntry(BaseModel):
    """An entry in the audit log — every query is logged."""

    id: int | None = None
    timestamp: datetime | None = None
    uc_id: str | None = None
    tier: str  # T0, T1, T2, T3
    query_text: str = ""
    composed_sql: str | None = None
    latency_ms: float = 0
    rows_returned: int = 0
    agent_id: str | None = None
    cost_units: float = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComposedQuery(BaseModel):
    """Result of T2 SQL composition from table metadata."""

    sql: str
    params: list = Field(default_factory=list)
    estimated_rows: int | None = None
    estimated_cost_units: float | None = None
    source_tables: list[str] = []
    confidence: float = 0.0  # 0.0 - 1.0


class QueryResult(BaseModel):
    """The response from the CogniMesh gateway — includes data + metadata."""

    data: list[dict[str, Any]] = Field(default_factory=list)
    tier: Literal["T0", "T1", "T2", "T3"]
    uc_id: str | None = None
    lineage: list[ColumnLineage] | None = None
    freshness: FreshnessInfo | None = None
    composed_sql: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityDescriptor(BaseModel):
    """Agent-facing description of a capability (for discovery)."""

    uc_id: str
    question: str
    parameters: list[str] = []
    freshness_guarantee_seconds: int = 0
    access_pattern: str = ""
    available_fields: list[str] = []
