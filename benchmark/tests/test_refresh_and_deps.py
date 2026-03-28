"""Tests for smart refresh and dependency flow reporting."""
import pytest  # noqa: F401


class TestDependencyReporting:
    """Test the dependency flow APIs."""

    def test_full_graph(self, mesh_app):
        """GET /dependencies returns the full Silver -> Gold -> UC graph."""
        r = mesh_app.get("/dependencies")
        assert r.status_code == 200
        graph = r.json()

        # Should have silver_tables, gold_views, ucs, summary
        assert "silver_tables" in graph
        assert "gold_views" in graph
        assert "ucs" in graph
        assert "summary" in graph

        # Summary should show consolidation
        summary = graph["summary"]
        assert summary["uc_count"] >= 3
        assert summary["gold_view_count"] < summary["uc_count"]  # consolidation!
        print(f"  Graph: {summary['silver_table_count']} Silver -> {summary['gold_view_count']} Gold -> {summary['uc_count']} UCs")
        print(f"  Consolidation ratio: {summary['consolidation_ratio']}")

    def test_impact_analysis_table(self, mesh_app):
        """What breaks if customer_profiles changes?"""
        r = mesh_app.get("/dependencies/impact", params={"table": "silver.customer_profiles"})
        assert r.status_code == 200
        impact = r.json()

        # Should show customer_360 is affected
        affected_views = [i["gold_view"] for i in impact]
        assert any("customer_360" in v for v in affected_views), f"Expected customer_360 in {affected_views}"

        # Should show multiple UCs affected
        total_ucs = sum(i["affected_uc_count"] for i in impact)
        assert total_ucs >= 2
        print(f"  Changing customer_profiles affects {len(affected_views)} Gold view(s), {total_ucs} UC(s)")

    def test_impact_analysis_column(self, mesh_app):
        """What breaks if customer_profiles.ltv_segment specifically changes?"""
        r = mesh_app.get("/dependencies/impact", params={
            "table": "silver.customer_profiles",
            "column": "ltv_segment"
        })
        assert r.status_code == 200
        impact = r.json()
        assert len(impact) > 0
        # ltv_segment should map to at least one Gold column
        for item in impact:
            print(f"  {item['gold_view']}: {item['affected_column_count']} columns affected, {item['affected_uc_count']} UCs")

    def test_provenance_view(self, mesh_app):
        """Where does customer_360 come from?"""
        r = mesh_app.get("/dependencies/provenance", params={"view": "gold_cognimesh.customer_360"})
        assert r.status_code == 200
        prov = r.json()
        assert len(prov) > 0
        # Should show silver.customer_profiles as source
        source_tables = set(p.get("source_table", "") for p in prov)
        assert any("customer_profiles" in t for t in source_tables)
        print(f"  customer_360 sources: {source_tables}")

    def test_provenance_column(self, mesh_app):
        """Where does customer_360.health_status come from?"""
        r = mesh_app.get("/dependencies/provenance", params={
            "view": "gold_cognimesh.customer_360",
            "column": "health_status"
        })
        assert r.status_code == 200
        prov = r.json()
        assert len(prov) > 0
        # health_status is computed from days_since_last_order
        print(f"  health_status lineage: {prov}")

    def test_what_if(self, mesh_app):
        """What would happen if customer_profiles changes?"""
        r = mesh_app.get("/dependencies/what-if", params={"table": "silver.customer_profiles"})
        assert r.status_code == 200
        result = r.json()

        assert "affected_gold_views" in result
        assert "affected_ucs" in result
        assert "message" in result
        assert result["affected_gold_view_count"] >= 1
        assert result["affected_uc_count"] >= 2
        print(f"  What-if: {result['message']}")


class TestRefreshManagement:
    """Test smart refresh features."""

    def test_refresh_status(self, mesh_app):
        """GET /refresh/status returns freshness of all Gold views."""
        r = mesh_app.get("/refresh/status")
        assert r.status_code == 200
        status = r.json()
        assert len(status) >= 1

        for view in status:
            assert "gold_view" in view
            assert "age_seconds" in view
            assert "ttl_seconds" in view
            assert "is_stale" in view
            assert "serves_ucs" in view
            print(f"  {view['gold_view']}: age={view['age_seconds']:.0f}s, ttl={view['ttl_seconds']}s, stale={view['is_stale']}, serves {view['uc_count']} UCs")

    def test_refresh_plan(self, mesh_app):
        """GET /refresh/plan returns what would be refreshed."""
        r = mesh_app.get("/refresh/plan")
        assert r.status_code == 200
        plan = r.json()
        # Plan may be empty if nothing is stale -- that's OK
        print(f"  Refresh plan: {len(plan)} view(s) would be refreshed")

    def test_refresh_stale_views(self, mesh_app, db_conn):
        """Manually expire a TTL, then check_and_refresh refreshes it."""
        # Set a very short TTL and backdate the refresh
        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE cognimesh_internal.freshness SET ttl_seconds = 1, last_refreshed_at = now() - interval '10 seconds' "
                "WHERE gold_view = 'gold_cognimesh.customer_360'"
            )
        db_conn.commit()

        try:
            # Check refresh plan -- should show customer_360 as stale
            r = mesh_app.get("/refresh/plan")
            assert r.status_code == 200
            plan = r.json()
            stale_views = [p["gold_view"] for p in plan]
            assert "gold_cognimesh.customer_360" in stale_views, f"Expected customer_360 in stale list: {stale_views}"

            # Execute refresh
            r = mesh_app.post("/refresh/check")
            assert r.status_code == 200
            result = r.json()
            assert "gold_cognimesh.customer_360" in result
            print(f"  Refreshed: {result}")
        finally:
            # Restore TTL
            with db_conn.cursor() as cur:
                cur.execute(
                    "UPDATE cognimesh_internal.freshness SET ttl_seconds = 14400, last_refreshed_at = now() "
                    "WHERE gold_view = 'gold_cognimesh.customer_360'"
                )
            db_conn.commit()

    def test_silver_change_detection(self, mesh_app, db_conn):
        """Verify that changing Silver data flags the correct Gold views for refresh."""
        # This tests the on_silver_change logic directly, not LISTEN/NOTIFY
        # (LISTEN/NOTIFY requires a persistent connection which is hard in a test)

        # Simulate: customer_profiles changed -> what needs refresh?
        r = mesh_app.get("/dependencies/what-if", params={"table": "silver.customer_profiles"})
        assert r.status_code == 200
        result = r.json()

        # customer_profiles change should affect customer_360 (serving 10 UCs)
        assert "gold_cognimesh.customer_360" in result["affected_gold_views"]
        # Should NOT affect product_catalog or order_analytics
        assert "gold_cognimesh.product_catalog" not in result["affected_gold_views"]
        assert "gold_cognimesh.order_analytics" not in result["affected_gold_views"]

        print(f"  customer_profiles change -> {result['affected_gold_view_count']} view(s), {result['affected_uc_count']} UC(s)")
        print(f"  Affected views: {result['affected_gold_views']}")
        print(f"  Affected UCs: {result['affected_ucs']}")


class TestRESTLacksDependencies:
    """Prove REST has NONE of these capabilities."""

    def test_rest_no_dependencies(self, rest_app):
        r = rest_app.get("/dependencies")
        assert r.status_code == 404

    def test_rest_no_impact_analysis(self, rest_app):
        r = rest_app.get("/dependencies/impact", params={"table": "silver.customer_profiles"})
        assert r.status_code in (404, 405)

    def test_rest_no_refresh_status(self, rest_app):
        r = rest_app.get("/refresh/status")
        assert r.status_code == 404

    def test_rest_no_refresh_check(self, rest_app):
        r = rest_app.post("/refresh/check")
        assert r.status_code in (404, 405)
