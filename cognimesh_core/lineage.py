"""Lineage Tracker — column-level lineage for Gold views."""

from __future__ import annotations

from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.db import get_connection
from cognimesh_core.models import ColumnLineage


class LineageTracker:
    """Registers and queries column-level lineage mappings."""

    def __init__(self, config: CogniMeshConfig):
        self.config = config

    def register_lineage(self, gold_view: str, mappings: list[ColumnLineage]) -> None:
        """Insert lineage mappings into cognimesh_internal.lineage.

        Uses UPSERT (ON CONFLICT DO UPDATE) to handle re-registration on refresh.
        """
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                for m in mappings:
                    cur.execute(
                        """
                        INSERT INTO cognimesh_internal.lineage
                            (gold_view, gold_column, source_table,
                             source_column, transformation, model_version)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (gold_view, gold_column, source_table, source_column)
                        DO UPDATE SET
                            transformation = EXCLUDED.transformation,
                            model_version = EXCLUDED.model_version,
                            registered_at = now()
                        """,
                        (
                            gold_view,
                            m.gold_column,
                            m.source_table,
                            m.source_column,
                            m.transformation,
                            m.model_version,
                        ),
                    )
            conn.commit()

    def get_lineage(self, gold_view: str) -> list[ColumnLineage]:
        """Get all column lineage for a Gold view."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT gold_column, source_table, source_column,
                           transformation, model_version
                    FROM cognimesh_internal.lineage
                    WHERE gold_view = %s
                    ORDER BY gold_column
                    """,
                    (gold_view,),
                )
                rows = cur.fetchall()
        return [
            ColumnLineage(
                gold_column=r["gold_column"],
                source_table=r["source_table"],
                source_column=r["source_column"],
                transformation=r.get("transformation"),
                model_version=r.get("model_version"),
            )
            for r in rows
        ]

    def get_column_lineage(
        self, gold_view: str, column: str
    ) -> ColumnLineage | None:
        """Get lineage for a specific column."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT gold_column, source_table, source_column,
                           transformation, model_version
                    FROM cognimesh_internal.lineage
                    WHERE gold_view = %s AND gold_column = %s
                    """,
                    (gold_view, column),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return ColumnLineage(
            gold_column=row["gold_column"],
            source_table=row["source_table"],
            source_column=row["source_column"],
            transformation=row.get("transformation"),
            model_version=row.get("model_version"),
        )
