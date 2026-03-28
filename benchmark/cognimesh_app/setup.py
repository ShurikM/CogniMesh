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

        # 1. Register the UC in the capability index
        registry.register(uc)

        # 2. Refresh Gold view — only once per consolidated view
        row_count = 0
        if uc.gold_view and uc.gold_view not in refreshed_views:
            row_count = gold_mgr.refresh_gold(uc)
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
