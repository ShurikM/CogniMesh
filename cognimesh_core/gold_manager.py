"""Gold Manager — derive, refresh, and introspect Gold views."""

from __future__ import annotations

import time

from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.db import get_connection
from cognimesh_core.models import FreshnessInfo, UseCase


class GoldManager:
    """Manages the lifecycle of Gold tables derived from Silver sources."""

    def __init__(self, config: CogniMeshConfig):
        self.config = config

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh_gold(self, uc: UseCase) -> int:
        """Refresh a Gold table from Silver using the UC's derivation_sql.

        Returns the row count.  Updates cognimesh_internal.freshness.
        """
        if not uc.gold_view or not uc.derivation_sql:
            raise ValueError(f"UC {uc.id} has no gold_view or derivation_sql")

        start_ms = time.perf_counter()

        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                # 1. Truncate the Gold table
                # gold_view comes from the registry (not user input)
                cur.execute(
                    "TRUNCATE TABLE {gold_view}".format(gold_view=uc.gold_view)
                )

                # 2. Execute the derivation SQL (INSERT...SELECT from Silver)
                cur.execute(uc.derivation_sql)

                # 3. Count rows
                cur.execute(
                    "SELECT count(*) AS cnt FROM {gold_view}".format(
                        gold_view=uc.gold_view
                    )
                )
                row_count: int = cur.fetchone()["cnt"]

                # 4. Update freshness record
                elapsed_ms = (time.perf_counter() - start_ms) * 1000
                cur.execute(
                    """
                    INSERT INTO cognimesh_internal.freshness
                        (gold_view, uc_id, last_refreshed_at, ttl_seconds,
                         row_count, refresh_duration_ms)
                    VALUES (%s, %s, now(), %s, %s, %s)
                    ON CONFLICT (gold_view) DO UPDATE SET
                        last_refreshed_at = now(),
                        ttl_seconds = EXCLUDED.ttl_seconds,
                        row_count = EXCLUDED.row_count,
                        refresh_duration_ms = EXCLUDED.refresh_duration_ms
                    """,
                    (
                        uc.gold_view,
                        uc.id,
                        uc.freshness_ttl_seconds,
                        row_count,
                        round(elapsed_ms, 2),
                    ),
                )
            conn.commit()

        return row_count

    def refresh_all(self, registry) -> dict[str, int]:
        """Refresh all active Gold views.  Returns {gold_view: row_count}."""
        results: dict[str, int] = {}
        for uc in registry.list_active():
            if uc.gold_view and uc.derivation_sql:
                results[uc.gold_view] = self.refresh_gold(uc)
        return results

    # ------------------------------------------------------------------
    # Freshness
    # ------------------------------------------------------------------

    def get_freshness(self, gold_view: str) -> FreshnessInfo:
        """Check freshness of a Gold view from cognimesh_internal.freshness."""
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT gold_view, last_refreshed_at, ttl_seconds,
                           EXTRACT(EPOCH FROM (now() - last_refreshed_at)) AS age_seconds
                    FROM cognimesh_internal.freshness
                    WHERE gold_view = %s
                    """,
                    (gold_view,),
                )
                row = cur.fetchone()

        if row is None:
            return FreshnessInfo(gold_view=gold_view, is_stale=True)

        age = float(row["age_seconds"]) if row["age_seconds"] is not None else 0.0
        ttl = int(row["ttl_seconds"])
        return FreshnessInfo(
            gold_view=row["gold_view"],
            last_refreshed_at=row["last_refreshed_at"],
            ttl_seconds=ttl,
            age_seconds=age,
            is_stale=age > ttl,
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_table_metadata(self) -> list[dict]:
        """Read table metadata from information_schema for Silver tables.

        Returns column names, types, table names -- used by T2 query composer.
        """
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_schema, table_name, column_name,
                           data_type, ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema = %s
                    ORDER BY table_schema, table_name, ordinal_position
                    """,
                    (self.config.silver_schema,),
                )
                rows = cur.fetchall()
        return rows
