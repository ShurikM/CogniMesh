"""Register CogniMesh UCs and derive Gold views.

Supports consolidated Gold views — multiple UCs can share the same Gold
view.  Each view is refreshed only once even when many UCs reference it.
"""

from __future__ import annotations

import glob
import json
import logging
import os

from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.db import get_connection
from cognimesh_core.gold_manager import GoldManager
from cognimesh_core.lineage import LineageTracker
from cognimesh_core.models import ColumnLineage, UseCase
from cognimesh_core.registry import UCRegistry

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Source-table mapping per Gold view (used for auto-lineage)
# ------------------------------------------------------------------
GOLD_VIEW_SOURCES: dict[str, str] = {
    "gold_cognimesh.customer_360": "silver.customer_profiles",
    "gold_cognimesh.product_catalog": "silver.product_metrics",
    "gold_cognimesh.order_analytics": "silver.orders_enriched",
    "gold_cognimesh.customer_orders": "silver.orders_enriched",
}


def _auto_lineage(uc: UseCase) -> list[ColumnLineage]:
    """Generate simple column-level lineage for a UC.

    Each required field is mapped as a direct pass-through from the first
    source table listed in the UC definition (or from the view-level
    default).  Override this with explicit lineage when transformations
    are involved.
    """
    source_table = (
        uc.source_tables[0]
        if uc.source_tables
        else GOLD_VIEW_SOURCES.get(uc.gold_view or "", "unknown")
    )
    return [
        ColumnLineage(
            gold_column=field,
            source_table=source_table,
            source_column=field,
            transformation="direct",
        )
        for field in uc.required_fields
    ]


def main() -> None:
    config = CogniMeshConfig()
    registry = UCRegistry(config)
    gold_mgr = GoldManager(config)
    lineage = LineageTracker(config)

    # Track which Gold views have already been refreshed so we only
    # materialise each consolidated view once.
    refreshed_views: set[str] = set()

    uc_dir = os.path.join(os.path.dirname(__file__), "use_cases")
    uc_count = 0
    for path in sorted(glob.glob(os.path.join(uc_dir, "*.json"))):
        with open(path) as f:
            data = json.load(f)
        uc = UseCase(**data)
        uc_count += 1

        # If the JSON has placeholder derivation_sql, preserve whatever real
        # SQL is already stored in the registry (written by seed_scale.py).
        if uc.derivation_sql and uc.derivation_sql.strip().startswith("--"):
            existing = registry.get(uc.id)
            if existing and existing.derivation_sql and not existing.derivation_sql.strip().startswith("--"):
                uc.derivation_sql = existing.derivation_sql

        # 1. Register the UC in the capability index
        registry.register(uc)

        # 2. Refresh Gold view — only once per consolidated view.
        #    Skip when derivation_sql is a placeholder comment (data already
        #    populated by seed_scale.py); refreshing would TRUNCATE the table
        #    and re-insert nothing.
        row_count = 0
        has_real_sql = (
            uc.derivation_sql
            and not uc.derivation_sql.strip().startswith("--")
        )
        if uc.gold_view and uc.gold_view not in refreshed_views:
            if has_real_sql:
                row_count = gold_mgr.refresh_gold(uc)
            else:
                # Gold table already populated by seed_scale.py — just record
                # the freshness metadata without truncating.
                with get_connection(config) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT count(*) AS cnt FROM {gv}".format(  # noqa: S608
                                gv=uc.gold_view
                            )
                        )
                        row_count = cur.fetchone()["cnt"]
                        cur.execute(
                            """
                            INSERT INTO cognimesh_internal.freshness
                                (gold_view, uc_id, last_refreshed_at, ttl_seconds,
                                 row_count, refresh_duration_ms)
                            VALUES (%s, %s, now(), %s, %s, 0)
                            ON CONFLICT (gold_view) DO UPDATE SET
                                last_refreshed_at = now(),
                                ttl_seconds = EXCLUDED.ttl_seconds,
                                row_count = EXCLUDED.row_count,
                                refresh_duration_ms = EXCLUDED.refresh_duration_ms
                            """,
                            (uc.gold_view, uc.id, uc.freshness_ttl_seconds, row_count),
                        )
                    conn.commit()
            refreshed_views.add(uc.gold_view)

        # 3. Register column-level lineage
        mappings = _auto_lineage(uc)
        if uc.gold_view:
            lineage.register_lineage(uc.gold_view, mappings)

        status = "refreshed" if row_count else "shared"
        logger.info(
            "Registered %s: %s (%s, %d rows)",
            uc.id, uc.gold_view, status, row_count,
        )

    # Summary
    logger.info(
        "Setup complete: %d Gold views, %d UCs.",
        len(refreshed_views), uc_count,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
