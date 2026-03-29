"""UC Registry — CRUD operations against cognimesh_internal.uc_registry."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.db import get_connection
from cognimesh_core.models import UseCase

if TYPE_CHECKING:
    from cognimesh_core.approval import ApprovalQueue


class UCRegistry:
    """Manages the Use Case registry in Postgres."""

    def __init__(self, config: CogniMeshConfig, approval_queue: ApprovalQueue | None = None):
        self.config = config
        self.approval_queue = approval_queue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, uc: UseCase, require_approval: bool = False, requested_by: str | None = None) -> UseCase:
        """Insert UC into registry. If require_approval=True, UC starts as pending_approval."""
        if require_approval and self.approval_queue:
            uc.status = "pending_approval"

        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cognimesh_internal.uc_registry
                        (id, question, consuming_agent, required_fields,
                         access_pattern, freshness_ttl_seconds, gold_view,
                         gold_schema, source_tables, derivation_sql, status,
                         allowed_agents)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        question = EXCLUDED.question,
                        consuming_agent = EXCLUDED.consuming_agent,
                        required_fields = EXCLUDED.required_fields,
                        access_pattern = EXCLUDED.access_pattern,
                        freshness_ttl_seconds = EXCLUDED.freshness_ttl_seconds,
                        gold_view = EXCLUDED.gold_view,
                        gold_schema = EXCLUDED.gold_schema,
                        source_tables = EXCLUDED.source_tables,
                        derivation_sql = EXCLUDED.derivation_sql,
                        status = EXCLUDED.status,
                        allowed_agents = EXCLUDED.allowed_agents,
                        updated_at = now()
                    RETURNING created_at, updated_at
                    """,
                    (
                        uc.id,
                        uc.question,
                        uc.consuming_agent,
                        json.dumps(uc.required_fields),
                        uc.access_pattern,
                        uc.freshness_ttl_seconds,
                        uc.gold_view,
                        uc.gold_schema,
                        json.dumps(uc.source_tables) if uc.source_tables else None,
                        uc.derivation_sql,
                        uc.status,
                        json.dumps(uc.allowed_agents) if uc.allowed_agents else None,
                    ),
                )
                row = cur.fetchone()
                uc.created_at = row["created_at"]
                uc.updated_at = row["updated_at"]

                # Log creation to change log
                self._log_change(cur, uc.id, "created", None, uc)
            conn.commit()

        if require_approval and self.approval_queue:
            self.approval_queue.submit(uc, action="register", requested_by=requested_by)

        return uc

    def get(self, uc_id: str) -> UseCase | None:
        """Get UC by ID."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM cognimesh_internal.uc_registry WHERE id = %s",
                    (uc_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_uc(row)

    def list_active(self) -> list[UseCase]:
        """List all active UCs."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM cognimesh_internal.uc_registry "
                    "WHERE status = 'active' ORDER BY id"
                )
                rows = cur.fetchall()
        return [self._row_to_uc(r) for r in rows]

    def update(self, uc: UseCase) -> UseCase:
        """Update UC. Log before/after to uc_change_log."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                # Fetch current state for before_state
                cur.execute(
                    "SELECT * FROM cognimesh_internal.uc_registry WHERE id = %s",
                    (uc.id,),
                )
                before_row = cur.fetchone()
                if before_row is None:
                    raise ValueError(f"UC {uc.id} not found")
                before_uc = self._row_to_uc(before_row)

                cur.execute(
                    """
                    UPDATE cognimesh_internal.uc_registry SET
                        question = %s,
                        consuming_agent = %s,
                        required_fields = %s,
                        access_pattern = %s,
                        freshness_ttl_seconds = %s,
                        gold_view = %s,
                        gold_schema = %s,
                        source_tables = %s,
                        derivation_sql = %s,
                        status = %s,
                        allowed_agents = %s,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING created_at, updated_at
                    """,
                    (
                        uc.question,
                        uc.consuming_agent,
                        json.dumps(uc.required_fields),
                        uc.access_pattern,
                        uc.freshness_ttl_seconds,
                        uc.gold_view,
                        uc.gold_schema,
                        json.dumps(uc.source_tables) if uc.source_tables else None,
                        uc.derivation_sql,
                        uc.status,
                        json.dumps(uc.allowed_agents) if uc.allowed_agents else None,
                        uc.id,
                    ),
                )
                row = cur.fetchone()
                uc.created_at = row["created_at"]
                uc.updated_at = row["updated_at"]

                # Log change
                self._log_change(cur, uc.id, "updated", before_uc, uc)
            conn.commit()
        return uc

    def deactivate(self, uc_id: str) -> None:
        """Set UC status to deprecated. Log change."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                # Fetch current state
                cur.execute(
                    "SELECT * FROM cognimesh_internal.uc_registry WHERE id = %s",
                    (uc_id,),
                )
                before_row = cur.fetchone()
                if before_row is None:
                    raise ValueError(f"UC {uc_id} not found")
                before_uc = self._row_to_uc(before_row)

                cur.execute(
                    """
                    UPDATE cognimesh_internal.uc_registry
                    SET status = 'deprecated', updated_at = now()
                    WHERE id = %s
                    RETURNING created_at, updated_at
                    """,
                    (uc_id,),
                )
                row = cur.fetchone()

                after_uc = before_uc.model_copy()
                after_uc.status = "deprecated"
                after_uc.updated_at = row["updated_at"]

                self._log_change(cur, uc_id, "deactivated", before_uc, after_uc)
            conn.commit()

    def activate(self, uc_id: str) -> UseCase | None:
        """Activate a pending UC (called after approval)."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE cognimesh_internal.uc_registry
                    SET status = 'active', updated_at = now()
                    WHERE id = %s AND status = 'pending_approval'
                    RETURNING *
                    """,
                    (uc_id,),
                )
                row = cur.fetchone()
                if row:
                    self._log_change(cur, uc_id, "activated", None, self._row_to_uc(row))
            conn.commit()
        return self._row_to_uc(row) if row else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_uc(row: dict) -> UseCase:
        """Convert a DB row dict to a UseCase model."""
        required_fields = row["required_fields"]
        if isinstance(required_fields, str):
            required_fields = json.loads(required_fields)

        source_tables = row.get("source_tables")
        if isinstance(source_tables, str):
            source_tables = json.loads(source_tables)

        allowed_agents = row.get("allowed_agents")
        if isinstance(allowed_agents, str):
            allowed_agents = json.loads(allowed_agents)

        return UseCase(
            id=row["id"],
            question=row["question"],
            consuming_agent=row.get("consuming_agent"),
            required_fields=required_fields,
            access_pattern=row["access_pattern"],
            freshness_ttl_seconds=row["freshness_ttl_seconds"],
            gold_view=row.get("gold_view"),
            gold_schema=row.get("gold_schema", "gold_cognimesh"),
            source_tables=source_tables,
            derivation_sql=row.get("derivation_sql"),
            status=row.get("status", "active"),
            allowed_agents=allowed_agents,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    @staticmethod
    def _log_change(
        cur,
        uc_id: str,
        change_type: str,
        before: UseCase | None,
        after: UseCase | None,
    ) -> None:
        """Insert an entry into cognimesh_internal.uc_change_log."""
        before_json = before.model_dump_json() if before else None
        after_json = after.model_dump_json() if after else None
        cur.execute(
            """
            INSERT INTO cognimesh_internal.uc_change_log
                (uc_id, change_type, before_state, after_state)
            VALUES (%s, %s, %s, %s)
            """,
            (uc_id, change_type, before_json, after_json),
        )
