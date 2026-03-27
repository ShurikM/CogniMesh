"""Register CogniMesh UCs and derive Gold views."""

from __future__ import annotations

import glob
import json
import os

from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.gold_manager import GoldManager
from cognimesh_core.lineage import LineageTracker
from cognimesh_core.models import ColumnLineage, UseCase
from cognimesh_core.registry import UCRegistry

# ------------------------------------------------------------------
# Column-level lineage for each UC
# ------------------------------------------------------------------
LINEAGE_MAPS: dict[str, list[dict]] = {
    "UC-01": [
        {
            "gold_column": "customer_id",
            "source_table": "silver.customer_profiles",
            "source_column": "customer_id",
            "transformation": "direct",
        },
        {
            "gold_column": "name",
            "source_table": "silver.customer_profiles",
            "source_column": "name",
            "transformation": "direct",
        },
        {
            "gold_column": "region",
            "source_table": "silver.customer_profiles",
            "source_column": "region",
            "transformation": "direct",
        },
        {
            "gold_column": "total_orders",
            "source_table": "silver.customer_profiles",
            "source_column": "total_orders",
            "transformation": "direct",
        },
        {
            "gold_column": "total_spend",
            "source_table": "silver.customer_profiles",
            "source_column": "total_spend",
            "transformation": "direct",
        },
        {
            "gold_column": "days_since_last_order",
            "source_table": "silver.customer_profiles",
            "source_column": "days_since_last_order",
            "transformation": "direct",
        },
        {
            "gold_column": "ltv_segment",
            "source_table": "silver.customer_profiles",
            "source_column": "ltv_segment",
            "transformation": "direct",
        },
        {
            "gold_column": "health_status",
            "source_table": "silver.customer_profiles",
            "source_column": "days_since_last_order",
            "transformation": (
                "computed: CASE WHEN days_since_last_order < 30 "
                "AND ltv_segment IN ('high','medium') THEN 'healthy' "
                "WHEN days_since_last_order < 90 THEN 'warning' "
                "ELSE 'critical' END"
            ),
        },
    ],
    "UC-02": [
        {
            "gold_column": "product_id",
            "source_table": "silver.product_metrics",
            "source_column": "product_id",
            "transformation": "direct",
        },
        {
            "gold_column": "category",
            "source_table": "silver.product_metrics",
            "source_column": "category",
            "transformation": "direct",
        },
        {
            "gold_column": "name",
            "source_table": "silver.product_metrics",
            "source_column": "name",
            "transformation": "direct",
        },
        {
            "gold_column": "price",
            "source_table": "silver.product_metrics",
            "source_column": "price",
            "transformation": "direct",
        },
        {
            "gold_column": "units_sold_30d",
            "source_table": "silver.product_metrics",
            "source_column": "units_sold_30d",
            "transformation": "direct",
        },
        {
            "gold_column": "revenue_30d",
            "source_table": "silver.product_metrics",
            "source_column": "revenue_30d",
            "transformation": "direct",
        },
        {
            "gold_column": "return_rate",
            "source_table": "silver.product_metrics",
            "source_column": "return_rate",
            "transformation": "direct",
        },
        {
            "gold_column": "rank_in_category",
            "source_table": "silver.product_metrics",
            "source_column": "revenue_30d",
            "transformation": (
                "computed: ROW_NUMBER() OVER "
                "(PARTITION BY category ORDER BY revenue_30d DESC)"
            ),
        },
    ],
    "UC-03": [
        {
            "gold_column": "customer_id",
            "source_table": "silver.customer_profiles",
            "source_column": "customer_id",
            "transformation": "direct",
        },
        {
            "gold_column": "name",
            "source_table": "silver.customer_profiles",
            "source_column": "name",
            "transformation": "direct",
        },
        {
            "gold_column": "region",
            "source_table": "silver.customer_profiles",
            "source_column": "region",
            "transformation": "direct",
        },
        {
            "gold_column": "days_since_last_order",
            "source_table": "silver.customer_profiles",
            "source_column": "days_since_last_order",
            "transformation": "direct",
        },
        {
            "gold_column": "ltv_segment",
            "source_table": "silver.customer_profiles",
            "source_column": "ltv_segment",
            "transformation": "direct",
        },
        {
            "gold_column": "total_spend",
            "source_table": "silver.customer_profiles",
            "source_column": "total_spend",
            "transformation": "direct",
        },
        {
            "gold_column": "risk_score",
            "source_table": "silver.customer_profiles",
            "source_column": "days_since_last_order",
            "transformation": (
                "computed: LEAST((days_since_last_order::NUMERIC / 365) * 50 "
                "+ CASE ltv_segment WHEN 'high' THEN 30 "
                "WHEN 'medium' THEN 15 ELSE 5 END, 99.99)"
            ),
        },
    ],
}


def main() -> None:
    config = CogniMeshConfig()
    registry = UCRegistry(config)
    gold_mgr = GoldManager(config)
    lineage = LineageTracker(config)

    uc_dir = os.path.join(os.path.dirname(__file__), "use_cases")
    for path in sorted(glob.glob(os.path.join(uc_dir, "*.json"))):
        with open(path) as f:
            data = json.load(f)
        uc = UseCase(**data)

        # Register UC
        registry.register(uc)

        # Refresh Gold view
        row_count = gold_mgr.refresh_gold(uc)

        # Register lineage
        if uc.id in LINEAGE_MAPS:
            mappings = [ColumnLineage(**m) for m in LINEAGE_MAPS[uc.id]]
            lineage.register_lineage(uc.gold_view, mappings)

        print(f"Registered {uc.id}: {uc.gold_view} ({row_count} rows)")

    print("Setup complete.")


if __name__ == "__main__":
    main()
