"""Approval queue — nothing changes in Gold without human approval.

Phase 1 invariant: "Nothing changes in Gold without human approval."

Flow:
  Register/update UC → status='pending_approval' → entry in approval_queue
  → Human reviews (GET /approvals)
  → Approves (POST /approvals/{id}/approve) → UC activated → Gold derived
  → Rejects (POST /approvals/{id}/reject) → UC stays inactive
"""
from __future__ import annotations

import json
import logging

from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.db import get_connection
from cognimesh_core.models import UseCase

logger = logging.getLogger(__name__)


class ApprovalQueue:
    """Manages the approval workflow for UC changes."""

    def __init__(self, config: CogniMeshConfig):
        self.config = config

    def submit(self, uc: UseCase, action: str, requested_by: str | None = None) -> int:
        """Submit a UC change for approval. Returns the approval queue ID."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cognimesh_internal.approval_queue
                        (uc_id, action, status, request_data, requested_by)
                    VALUES (%s, %s, 'pending', %s, %s)
                    RETURNING id
                    """,
                    (uc.id, action, json.dumps(uc.model_dump(), default=str), requested_by),
                )
                row = cur.fetchone()
                approval_id = row["id"]
            conn.commit()

        logger.info("Submitted %s for approval: UC %s (queue ID: %d)", action, uc.id, approval_id)
        return approval_id

    def list_pending(self) -> list[dict]:
        """List all pending approvals."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, uc_id, action, status, request_data,
                           requested_at, requested_by
                    FROM cognimesh_internal.approval_queue
                    WHERE status = 'pending'
                    ORDER BY requested_at
                    """
                )
                rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, approval_id: int) -> dict | None:
        """Get a specific approval by ID."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM cognimesh_internal.approval_queue WHERE id = %s",
                    (approval_id,),
                )
                row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    def approve(self, approval_id: int, reviewed_by: str | None = None, note: str | None = None) -> dict | None:
        """Approve a pending request. Returns the updated approval record."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE cognimesh_internal.approval_queue
                    SET status = 'approved',
                        reviewed_by = %s,
                        reviewed_at = now(),
                        review_note = %s
                    WHERE id = %s AND status = 'pending'
                    RETURNING *
                    """,
                    (reviewed_by, note, approval_id),
                )
                row = cur.fetchone()
            conn.commit()

        if row:
            logger.info("Approved queue ID %d (UC: %s)", approval_id, row["uc_id"])
            return self._row_to_dict(row)
        return None

    def reject(self, approval_id: int, reviewed_by: str | None = None, reason: str | None = None) -> dict | None:
        """Reject a pending request."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE cognimesh_internal.approval_queue
                    SET status = 'rejected',
                        reviewed_by = %s,
                        reviewed_at = now(),
                        review_note = %s
                    WHERE id = %s AND status = 'pending'
                    RETURNING *
                    """,
                    (reviewed_by, reason, approval_id),
                )
                row = cur.fetchone()
            conn.commit()

        if row:
            logger.info("Rejected queue ID %d (UC: %s): %s", approval_id, row["uc_id"], reason)
            return self._row_to_dict(row)
        return None

    def get_history(self, uc_id: str | None = None, limit: int = 50) -> list[dict]:
        """Get approval history, optionally filtered by UC."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                if uc_id:
                    cur.execute(
                        """
                        SELECT * FROM cognimesh_internal.approval_queue
                        WHERE uc_id = %s
                        ORDER BY requested_at DESC LIMIT %s
                        """,
                        (uc_id, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM cognimesh_internal.approval_queue
                        ORDER BY requested_at DESC LIMIT %s
                        """,
                        (limit,),
                    )
                rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _row_to_dict(self, row: dict) -> dict:
        """Convert a DB row to a clean dict."""
        result = dict(row)
        # Ensure datetime serialization
        for key in ("requested_at", "reviewed_at"):
            if key in result and result[key] is not None:
                result[key] = result[key].isoformat()
        return result
