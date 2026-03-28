"""Dependency flow reporting — impact analysis, provenance, and full graph.

Answers questions like:
- "What breaks if I change silver.customer_profiles?" (impact analysis)
- "Where does gold_cognimesh.customer_360.health_status come from?" (provenance)
- "Show me everything: Silver -> Gold -> UCs" (full graph)
"""
from __future__ import annotations

import logging
from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.db import get_connection
from cognimesh_core.lineage import LineageTracker
from cognimesh_core.registry import UCRegistry

logger = logging.getLogger(__name__)


class DependencyReporter:
    """Builds and exposes the full dependency graph from lineage + UC registry."""

    def __init__(self, config: CogniMeshConfig, lineage: LineageTracker, registry: UCRegistry):
        self.config = config
        self.lineage = lineage
        self.registry = registry

    def impact_analysis(self, silver_table: str, silver_column: str | None = None) -> list[dict]:
        """What Gold views/columns/UCs are affected by a change to this Silver table?

        Example: impact_analysis("silver.customer_profiles") returns:
        [
            {"gold_view": "gold_cognimesh.customer_360", "gold_column": "health_status",
             "transformation": "computed", "affected_ucs": ["UC-01", "UC-03", "UC-05", ...]},
            ...
        ]
        """
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                if silver_column:
                    cur.execute(
                        "SELECT gold_view, gold_column, transformation "
                        "FROM cognimesh_internal.lineage "
                        "WHERE source_table = %s AND source_column = %s "
                        "ORDER BY gold_view, gold_column",
                        (silver_table, silver_column)
                    )
                else:
                    cur.execute(
                        "SELECT gold_view, gold_column, transformation "
                        "FROM cognimesh_internal.lineage "
                        "WHERE source_table = %s "
                        "ORDER BY gold_view, gold_column",
                        (silver_table,)
                    )
                rows = cur.fetchall()

        # Group by gold_view
        views: dict[str, list[dict]] = {}
        for row in rows:
            gv = row["gold_view"]
            if gv not in views:
                views[gv] = []
            views[gv].append({
                "gold_column": row["gold_column"],
                "transformation": row["transformation"],
            })

        # Find affected UCs for each gold_view
        all_ucs = self.registry.list_active()
        results = []
        for gold_view, columns in views.items():
            affected_ucs = [uc.id for uc in all_ucs if uc.gold_view == gold_view]
            results.append({
                "gold_view": gold_view,
                "affected_columns": columns,
                "affected_column_count": len(columns),
                "affected_ucs": affected_ucs,
                "affected_uc_count": len(affected_ucs),
            })

        return results

    def provenance(self, gold_view: str, gold_column: str | None = None) -> list[dict]:
        """Where does this Gold column come from?

        Example: provenance("gold_cognimesh.customer_360", "health_status") returns:
        [{"source_table": "silver.customer_profiles", "source_column": "days_since_last_order",
          "transformation": "computed"}]
        """
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                if gold_column:
                    cur.execute(
                        "SELECT source_table, source_column, transformation, model_version "
                        "FROM cognimesh_internal.lineage "
                        "WHERE gold_view = %s AND gold_column = %s",
                        (gold_view, gold_column)
                    )
                else:
                    cur.execute(
                        "SELECT gold_column, source_table, source_column, transformation, model_version "
                        "FROM cognimesh_internal.lineage "
                        "WHERE gold_view = %s ORDER BY gold_column",
                        (gold_view,)
                    )
                rows = cur.fetchall()

        return [dict(r) for r in rows]

    def full_graph(self) -> dict:
        """Full dependency graph: Silver -> Gold -> UCs.

        Returns a structured tree showing the entire data flow.
        """
        # Get all lineage
        with get_connection(self.config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT gold_view, gold_column, source_table, source_column, transformation "
                    "FROM cognimesh_internal.lineage ORDER BY source_table, gold_view, gold_column"
                )
                lineage_rows = cur.fetchall()

        # Get all active UCs
        all_ucs = self.registry.list_active()

        # Build Silver tables map
        silver_tables: dict[str, dict] = {}
        for row in lineage_rows:
            st = row["source_table"]
            if st not in silver_tables:
                silver_tables[st] = {"name": st, "columns": set(), "feeds_gold_views": set()}
            silver_tables[st]["columns"].add(row["source_column"])
            silver_tables[st]["feeds_gold_views"].add(row["gold_view"])

        # Build Gold views map
        gold_views: dict[str, dict] = {}
        for row in lineage_rows:
            gv = row["gold_view"]
            if gv not in gold_views:
                gold_views[gv] = {"name": gv, "source_tables": set(), "columns": set(), "serves_ucs": []}
            gold_views[gv]["source_tables"].add(row["source_table"])
            gold_views[gv]["columns"].add(row["gold_column"])

        # Map UCs to Gold views
        for uc in all_ucs:
            if uc.gold_view and uc.gold_view in gold_views:
                gold_views[uc.gold_view]["serves_ucs"].append({
                    "id": uc.id,
                    "question": uc.question,
                    "required_fields": uc.required_fields,
                })

        # Convert sets to sorted lists for JSON serialization
        silver_list = []
        for st in silver_tables.values():
            silver_list.append({
                "name": st["name"],
                "columns": sorted(st["columns"]),
                "feeds_gold_views": sorted(st["feeds_gold_views"]),
            })

        gold_list = []
        for gv in gold_views.values():
            gold_list.append({
                "name": gv["name"],
                "source_tables": sorted(gv["source_tables"]),
                "columns": sorted(gv["columns"]),
                "serves_ucs": gv["serves_ucs"],
                "uc_count": len(gv["serves_ucs"]),
            })

        return {
            "silver_tables": sorted(silver_list, key=lambda x: x["name"]),
            "gold_views": sorted(gold_list, key=lambda x: x["name"]),
            "ucs": [{"id": uc.id, "question": uc.question, "gold_view": uc.gold_view} for uc in all_ucs],
            "summary": {
                "silver_table_count": len(silver_tables),
                "gold_view_count": len(gold_views),
                "uc_count": len(all_ucs),
                "consolidation_ratio": round(len(gold_views) / max(len(all_ucs), 1), 2),
            }
        }

    def what_if(self, silver_table: str) -> dict:
        """What would happen if this Silver table changes?

        Returns affected Gold views, affected UCs, and estimated refresh impact.
        """
        impact = self.impact_analysis(silver_table)

        all_affected_ucs = []
        all_affected_views = []
        for item in impact:
            all_affected_views.append(item["gold_view"])
            all_affected_ucs.extend(item["affected_ucs"])

        # Get freshness info for affected views
        from cognimesh_core.gold_manager import GoldManager
        gm = GoldManager(self.config)
        freshness_info = []
        for view in all_affected_views:
            f = gm.get_freshness(view)
            freshness_info.append({
                "gold_view": view,
                "age_seconds": f.age_seconds,
                "ttl_seconds": f.ttl_seconds,
                "is_stale": f.is_stale,
            })

        return {
            "silver_table": silver_table,
            "affected_gold_views": all_affected_views,
            "affected_gold_view_count": len(all_affected_views),
            "affected_ucs": sorted(set(all_affected_ucs)),
            "affected_uc_count": len(set(all_affected_ucs)),
            "freshness": freshness_info,
            "message": f"Changing {silver_table} would require refreshing {len(all_affected_views)} Gold view(s) affecting {len(set(all_affected_ucs))} UC(s).",
        }
