"""CogniMesh Gateway — the T0/T1/T2/T3 query router.

T0: UC match found, Gold view exists and fresh -> SELECT from Gold.
T1: (reserved) Fields across multiple Gold views -> compose.
T2: No Gold coverage -> Silver fallback with guardrails.
T3: Exceeds guardrails or cannot compose -> reject with explanation.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from cognimesh_core.audit import AuditLog
from cognimesh_core.capability_index import CapabilityIndex
from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.db import get_connection
from cognimesh_core.gold_manager import GoldManager
from cognimesh_core.lineage import LineageTracker
from cognimesh_core.models import AuditEntry, ComposedQuery, QueryResult, UseCase
from cognimesh_core.query_composer import QueryComposer, TemplateComposer
from cognimesh_core.registry import UCRegistry

logger = logging.getLogger(__name__)


class Gateway:
    """Routes queries through the CogniMesh tier hierarchy."""

    def __init__(
        self,
        config: CogniMeshConfig,
        registry: UCRegistry,
        capability_index: CapabilityIndex,
        gold_manager: GoldManager,
        lineage_tracker: LineageTracker,
        audit_log: AuditLog,
        query_composer: QueryComposer | None = None,
    ):
        self.config = config
        self.registry = registry
        self.capability_index = capability_index
        self.gold_manager = gold_manager
        self.lineage = lineage_tracker
        self.audit = audit_log
        self.query_composer: QueryComposer = query_composer or TemplateComposer(config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(
        self,
        question: str,
        uc_id: str | None = None,
        params: dict | None = None,
        agent_id: str | None = None,
    ) -> QueryResult:
        """Route a query through the tier hierarchy.

        T0: UC match found, Gold view exists and fresh -> SELECT from Gold
        T1: (reserved) Fields across multiple Gold views -> compose
        T2: No Gold coverage -> Silver fallback with guardrails
        T3: Exceeds guardrails or cannot compose -> reject with explanation
        """
        start = time.perf_counter()
        agent_id = agent_id or self.config.default_agent_id

        # Resolve UC
        if uc_id:
            uc = self.capability_index.match_by_id(uc_id)
            confidence = 1.0
        else:
            uc, confidence = self.capability_index.match_question(question)

        # T0: exact match with Gold view
        if uc and confidence > 0.6 and uc.gold_view:
            result = self._serve_t0(uc, params)
            self._log_audit(uc.id, "T0", question, result, start, agent_id)
            return result

        # T1: (reserved for cross-Gold-view composition — skip to T2)

        # T2: Silver fallback with guardrails
        table_metadata = self.gold_manager.get_table_metadata()
        composed = self.query_composer.compose(question, table_metadata)
        if composed and composed.confidence >= 0.3:
            # Check guardrails before executing
            if self._within_guardrails(composed):
                result = self._serve_t2(composed, question, agent_id)
                self._log_audit(
                    None, result.tier, question, result, start, agent_id,
                )
                return result

            # T3: query composable but exceeds guardrails
            result = self._reject_t3(
                question, composed, reason="guardrails_exceeded",
            )
            self._log_audit(None, "T3", question, result, start, agent_id)
            return result

        # T3: cannot compose a query at all
        result = self._reject_t3(
            question, composed, reason="cannot_compose",
        )
        self._log_audit(None, "T3", question, result, start, agent_id)
        return result

    # ------------------------------------------------------------------
    # T0: Serve from Gold
    # ------------------------------------------------------------------

    def _serve_t0(self, uc: UseCase, params: dict | None) -> QueryResult:
        """Serve from Gold table directly.

        Handles three access patterns:
        - individual_lookup: WHERE primary_key = value
        - bulk_query: WHERE filter = value ORDER BY sort LIMIT n
        - aggregation: full scan with optional WHERE, LIMIT 1000
        """
        params = params or {}
        # gold_view is guaranteed non-None by caller (checked uc.gold_view)
        gold_view: str = uc.gold_view  # type: ignore[assignment]

        sql, query_params = self._build_gold_query(gold_view, uc, params)

        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, query_params)
                rows = cur.fetchall()

        # Convert rows to plain dicts (handle non-serializable types)
        data = [self._serialize_row(r) for r in rows]

        # Attach lineage
        lineage = self.lineage.get_lineage(gold_view)

        # Attach freshness
        freshness = self.gold_manager.get_freshness(gold_view)

        return QueryResult(
            data=data,
            tier="T0",
            uc_id=uc.id,
            lineage=lineage if lineage else None,
            freshness=freshness,
            metadata={"access_pattern": uc.access_pattern},
        )

    def _build_gold_query(
        self, gold_view: str, uc: UseCase, params: dict
    ) -> tuple[str, list[Any]]:
        """Build the SQL query for a Gold table based on access pattern."""
        if uc.access_pattern == "individual_lookup":
            return self._build_individual_lookup(gold_view, uc, params)
        elif uc.access_pattern == "bulk_query":
            return self._build_bulk_query(gold_view, uc, params)
        else:  # aggregation
            return self._build_aggregation(gold_view, uc, params)

    def _build_individual_lookup(
        self, gold_view: str, uc: UseCase, params: dict
    ) -> tuple[str, list[Any]]:
        """SELECT * FROM gold_view WHERE primary_key = %s."""
        # Find the primary key field (first field ending in _id)
        lookup_key = None
        for field in uc.required_fields:
            if field.endswith("_id"):
                lookup_key = field
                break
        if lookup_key is None:
            lookup_key = uc.required_fields[0]

        # Get the value from params
        value = params.get(lookup_key) or params.get("id")
        if value is None:
            # No filter — return all (capped)
            sql = "SELECT * FROM {gold_view} LIMIT 100".format(  # noqa: S608
                gold_view=gold_view
            )
            return sql, []

        sql = "SELECT * FROM {gold_view} WHERE {key} = %s".format(  # noqa: S608
            gold_view=gold_view, key=lookup_key
        )
        return sql, [value]

    def _build_bulk_query(
        self, gold_view: str, uc: UseCase, params: dict
    ) -> tuple[str, list[Any]]:
        """SELECT * FROM gold_view WHERE filter = %s ORDER BY sort LIMIT n."""
        limit = int(params.pop("limit", 100))
        sort_field = params.pop("sort", None)
        order = params.pop("order", "DESC")

        # Remaining params are filter fields
        filter_field = None
        filter_value = None
        for key, val in params.items():
            if key not in ("limit", "sort", "order") and val is not None:
                filter_field = key
                filter_value = val
                break

        # Default sort: pick a reasonable field from the UC
        if sort_field is None:
            # Try common sort fields
            for candidate in ("revenue_30d", "risk_score", "total_spend",
                              "rank_in_category", "days_since_last_order"):
                if candidate in uc.required_fields:
                    sort_field = candidate
                    break
            if sort_field is None:
                sort_field = uc.required_fields[-1]

        # Validate order direction
        order = order.upper()
        if order not in ("ASC", "DESC"):
            order = "DESC"

        query_params: list[Any] = []

        if filter_field and filter_value is not None:
            sql = (  # noqa: S608
                "SELECT * FROM {gold_view} WHERE {filter_field} = %s "
                "ORDER BY {sort_field} {order} LIMIT %s"
            ).format(
                gold_view=gold_view,
                filter_field=filter_field,
                sort_field=sort_field,
                order=order,
            )
            query_params = [filter_value, limit]
        else:
            sql = (  # noqa: S608
                "SELECT * FROM {gold_view} "
                "ORDER BY {sort_field} {order} LIMIT %s"
            ).format(
                gold_view=gold_view,
                sort_field=sort_field,
                order=order,
            )
            query_params = [limit]

        return sql, query_params

    def _build_aggregation(
        self, gold_view: str, uc: UseCase, params: dict
    ) -> tuple[str, list[Any]]:
        """SELECT * FROM gold_view [WHERE ...] LIMIT 1000."""
        query_params: list[Any] = []
        where_clauses: list[str] = []

        for key, val in params.items():
            if key not in ("limit",) and val is not None:
                where_clauses.append("{key} = %s".format(key=key))
                query_params.append(val)

        limit = int(params.get("limit", 1000))
        query_params.append(limit)

        if where_clauses:
            where = " WHERE " + " AND ".join(where_clauses)
        else:
            where = ""

        sql = "SELECT * FROM {gold_view}{where} LIMIT %s".format(  # noqa: S608
            gold_view=gold_view, where=where
        )
        return sql, query_params

    # ------------------------------------------------------------------
    # T2: Silver fallback with guardrails
    # ------------------------------------------------------------------

    def _within_guardrails(self, composed: ComposedQuery) -> bool:
        """Check T2 guardrails: max_rows, max_cost_units."""
        if (
            composed.estimated_rows is not None
            and composed.estimated_rows > self.config.t2_max_rows
        ):
            return False
        if (
            composed.estimated_cost_units is not None
            and composed.estimated_cost_units > self.config.t2_max_cost_units
        ):
            return False
        return True

    def _serve_t2(
        self, composed: ComposedQuery, question: str, agent_id: str
    ) -> QueryResult:
        """Execute T2 Silver fallback with timeout guardrail.

        Uses SET LOCAL statement_timeout to enforce the time limit.
        The query is wrapped in a try/except for graceful timeout handling.
        """
        timeout_ms = int(self.config.t2_max_seconds * 1000)

        try:
            with get_connection(self.config) as conn:
                with conn.cursor() as cur:
                    # SET LOCAL scopes the timeout to this transaction
                    cur.execute(
                        "SET LOCAL statement_timeout = %s", (timeout_ms,)  # noqa: S608
                    )
                    cur.execute(composed.sql)
                    rows = cur.fetchall()

            data = [self._serialize_row(r) for r in rows]

            return QueryResult(
                data=data,
                tier="T2",
                composed_sql=composed.sql,
                metadata={
                    "source_tables": composed.source_tables,
                    "confidence": composed.confidence,
                    "estimated_rows": composed.estimated_rows,
                    "actual_rows": len(data),
                    "note": (
                        "This was served via Silver fallback. "
                        "Consider promoting to a UC for optimal performance."
                    ),
                },
            )
        except Exception as exc:
            error_msg = str(exc)
            is_timeout = "canceling statement due to statement timeout" in error_msg

            logger.warning(
                "T2 query failed (%s): %s",
                "timeout" if is_timeout else "error",
                error_msg,
            )

            reason = "query_timeout" if is_timeout else "query_execution_error"
            return QueryResult(
                tier="T3",
                composed_sql=composed.sql,
                metadata={
                    "reason": reason,
                    "error": error_msg,
                    "source_tables": composed.source_tables,
                    "confidence": composed.confidence,
                    "estimated_rows": composed.estimated_rows,
                    "estimated_cost_units": composed.estimated_cost_units,
                    "suggestion": (
                        "Register this as a UC for optimal performance, "
                        "or adjust T2 guardrails if the cost is acceptable."
                    ),
                    "available_capabilities": [
                        d.uc_id for d in self.capability_index.discover()
                    ],
                },
            )

    # ------------------------------------------------------------------
    # T3: Structured rejection
    # ------------------------------------------------------------------

    def _reject_t3(
        self,
        question: str,
        composed: ComposedQuery | None,
        reason: str,
    ) -> QueryResult:
        """Structured T3 rejection with explanation.

        Provides context about why the query was rejected and what
        capabilities are available.
        """
        metadata: dict[str, Any] = {
            "reason": reason,
            "available_capabilities": [
                d.uc_id for d in self.capability_index.discover()
            ],
            "suggestion": (
                "Register this as a UC for optimal performance."
            ),
        }

        if composed is not None:
            metadata["composed_sql"] = composed.sql
            metadata["confidence"] = composed.confidence
            metadata["source_tables"] = composed.source_tables
            metadata["estimated_rows"] = composed.estimated_rows
            metadata["estimated_cost_units"] = composed.estimated_cost_units

            if reason == "guardrails_exceeded":
                metadata["guardrails"] = {
                    "max_rows": self.config.t2_max_rows,
                    "max_cost_units": self.config.t2_max_cost_units,
                    "max_seconds": self.config.t2_max_seconds,
                }
                metadata["suggestion"] = (
                    "Query exceeds T2 guardrails. Register as a UC with a "
                    "Gold view for optimal performance, or adjust guardrails."
                )

        return QueryResult(
            tier="T3",
            composed_sql=composed.sql if composed else None,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def _log_audit(
        self,
        uc_id: str | None,
        tier: str,
        question: str,
        result: QueryResult,
        start_time: float,
        agent_id: str,
    ) -> None:
        """Log to audit trail."""
        elapsed = (time.perf_counter() - start_time) * 1000
        entry = AuditEntry(
            uc_id=uc_id,
            tier=tier,
            query_text=question,
            composed_sql=result.composed_sql,
            latency_ms=elapsed,
            rows_returned=len(result.data),
            agent_id=agent_id,
            cost_units=self._compute_cost(tier, elapsed, len(result.data)),
        )
        self.audit.log_query(entry)

    @staticmethod
    def _compute_cost(tier: str, latency_ms: float, rows: int) -> float:
        """Simple cost model: T0=1, T1=5, T2=20, T3=0. Plus rows * 0.001."""
        base = {"T0": 1.0, "T1": 5.0, "T2": 20.0, "T3": 0.0}
        return base.get(tier, 0.0) + (rows * 0.001)

    @staticmethod
    def _serialize_row(row: dict) -> dict[str, Any]:
        """Convert a DB row dict to JSON-safe dict."""
        import uuid
        from datetime import date, datetime
        from decimal import Decimal

        out: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, Decimal):
                out[k] = float(v)
            elif isinstance(v, uuid.UUID):
                out[k] = str(v)
            elif isinstance(v, (datetime, date)):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out
