"""Audit Log — every gateway query is logged for governance and cost attribution."""

from __future__ import annotations

import json

from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.db import get_connection
from cognimesh_core.models import AuditEntry


class AuditLog:
    """Writes and reads the cognimesh_internal.audit_log table."""

    def __init__(self, config: CogniMeshConfig):
        self.config = config

    def log_query(self, entry: AuditEntry) -> None:
        """Insert audit entry into cognimesh_internal.audit_log."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cognimesh_internal.audit_log
                        (uc_id, tier, query_text, composed_sql,
                         latency_ms, rows_returned, agent_id,
                         cost_units, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entry.uc_id,
                        entry.tier,
                        entry.query_text,
                        entry.composed_sql,
                        entry.latency_ms,
                        entry.rows_returned,
                        entry.agent_id,
                        entry.cost_units,
                        json.dumps(entry.metadata),
                    ),
                )
            conn.commit()

    def get_trail(
        self,
        uc_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit log with optional filters."""
        clauses: list[str] = []
        params: list = []

        if uc_id is not None:
            clauses.append("uc_id = %s")
            params.append(uc_id)
        if agent_id is not None:
            clauses.append("agent_id = %s")
            params.append(agent_id)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        params.append(limit)

        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM cognimesh_internal.audit_log {where} "
                    "ORDER BY timestamp DESC LIMIT %s",
                    params,
                )
                rows = cur.fetchall()

        return [self._row_to_entry(r) for r in rows]

    def get_cost_by_uc(self) -> dict[str, float]:
        """Aggregate cost_units by UC -- for cost attribution."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT uc_id, COALESCE(SUM(cost_units), 0) AS total_cost
                    FROM cognimesh_internal.audit_log
                    WHERE uc_id IS NOT NULL
                    GROUP BY uc_id
                    ORDER BY total_cost DESC
                    """
                )
                rows = cur.fetchall()
        return {r["uc_id"]: float(r["total_cost"]) for r in rows}

    def get_cost_by_agent(self) -> dict[str, float]:
        """Aggregate cost_units by agent -- for cost attribution."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT agent_id, COALESCE(SUM(cost_units), 0) AS total_cost
                    FROM cognimesh_internal.audit_log
                    WHERE agent_id IS NOT NULL
                    GROUP BY agent_id
                    ORDER BY total_cost DESC
                    """
                )
                rows = cur.fetchall()
        return {r["agent_id"]: float(r["total_cost"]) for r in rows}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: dict) -> AuditEntry:
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return AuditEntry(
            id=row.get("id"),
            timestamp=row.get("timestamp"),
            uc_id=row.get("uc_id"),
            tier=row["tier"],
            query_text=row.get("query_text", ""),
            composed_sql=row.get("composed_sql"),
            latency_ms=float(row.get("latency_ms", 0)),
            rows_returned=int(row.get("rows_returned", 0)),
            agent_id=row.get("agent_id"),
            cost_units=float(row.get("cost_units", 0)),
            metadata=metadata,
        )
