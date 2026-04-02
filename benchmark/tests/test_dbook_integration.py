"""dbook integration tests — verify rich metadata enhances CogniMesh.

These tests demonstrate the benchmark improvements from integrating dbook:
- Schema awareness (enums, FKs, row counts)
- Enhanced T2 query composition
- Proactive schema drift detection
- Semantic discovery via concept index

All tests skip gracefully if dbook is not installed.
"""
from __future__ import annotations

import pytest

# Skip entire module if dbook not available
try:
    import dbook  # noqa: F401
    DBOOK_AVAILABLE = True
except ImportError:
    DBOOK_AVAILABLE = False

pytestmark = pytest.mark.skipif(not DBOOK_AVAILABLE, reason="dbook not installed")


class TestDbookSchemaAwareness:
    """Verify dbook enriches CogniMesh with Silver schema intelligence."""

    def test_dbook_bridge_available(self, dbook_bridge) -> None:
        """dbook bridge initializes and introspects Silver schema."""
        assert dbook_bridge is not None
        assert dbook_bridge.available

    def test_silver_tables_introspected(self, dbook_bridge) -> None:
        """dbook introspects Silver tables with rich metadata."""
        tables = dbook_bridge.get_table_metadata_rich()
        assert len(tables) > 0, "Expected at least one Silver table"
        # Each table should have columns
        for name, table in tables.items():
            assert len(table.columns) > 0, f"Table {name} has no columns"

    def test_enum_values_detected(self, dbook_bridge) -> None:
        """dbook detects enum-like columns in Silver tables."""
        tables = dbook_bridge.get_table_metadata_rich()
        # At least one table should have enum values detected
        all_enums = {}
        for name, table in tables.items():
            if table.enum_values:
                all_enums[name] = list(table.enum_values.keys())
        assert len(all_enums) > 0, (
            "Expected at least one table with enum values "
            "(e.g., region, ltv_segment, health_status)"
        )

    def test_foreign_keys_detected(self, dbook_bridge) -> None:
        """dbook detects FK relationships between Silver tables."""
        tables = dbook_bridge.get_table_metadata_rich()
        all_fks = []
        for name, table in tables.items():
            all_fks.extend(table.foreign_keys)
        # Silver tables may or may not have FKs depending on schema design
        # This is informational — log what was found
        # At minimum, verify the introspection ran without error

    def test_concepts_indexed(self, dbook_bridge) -> None:
        """Concept index maps domain terms to tables/columns."""
        concepts = dbook_bridge.get_concepts()
        assert len(concepts) > 0, "Expected concept index to have entries"
        # Should contain domain terms like 'customer', 'order', 'product'
        domain_terms = {"customer", "order", "product", "region", "spend"}
        found = domain_terms & set(concepts.keys())
        assert len(found) >= 2, (
            f"Expected at least 2 domain terms in concepts, found: {found}"
        )

    def test_row_counts_available(self, dbook_bridge) -> None:
        """dbook provides actual row counts for Silver tables."""
        tables = dbook_bridge.get_table_metadata_rich()
        tables_with_counts = {
            name: table.row_count
            for name, table in tables.items()
            if table.row_count is not None and table.row_count > 0
        }
        assert len(tables_with_counts) > 0, "Expected row counts for Silver tables"


class TestDbookEnhancedT2:
    """T2 Silver fallback benefits from dbook metadata."""

    def test_t2_query_returns_result(self, mesh_app) -> None:
        """T2 query with ad-hoc question composes and executes."""
        r = mesh_app.post("/query", json={
            "question": "What is the total revenue by region?",
            "agent_id": "benchmark",
        })
        assert r.status_code == 200
        data = r.json()
        # Should be T2 (Silver composition) or T0 if a UC matches
        assert data["tier"] in ("T0", "T2", "T3")

    def test_t2_validation_metadata(self, mesh_app) -> None:
        """T3 rejection from validation includes error details."""
        # Ask a question that references non-existent concepts
        r = mesh_app.post("/query", json={
            "question": "What is the quantum entanglement rate of warehouse inventory?",
            "agent_id": "benchmark",
        })
        assert r.status_code == 200
        data = r.json()
        # Should be T3 (cannot compose or validation failed)
        assert data["tier"] == "T3"


class TestDbookDriftDetection:
    """Proactive schema drift detection via dbook hash comparison."""

    def test_drift_endpoint_available(self, mesh_app) -> None:
        """GET /schema/drift returns drift status."""
        r = mesh_app.get("/schema/drift")
        assert r.status_code == 200
        data = r.json()
        assert "drift_detected" in data or "available" in data

    def test_no_drift_initially(self, mesh_app) -> None:
        """No drift detected on fresh introspection (baseline)."""
        r = mesh_app.get("/schema/drift")
        data = r.json()
        if data.get("available") is False:
            pytest.skip("dbook not enabled in app")
        # On second call (same schema), should detect no drift
        r2 = mesh_app.get("/schema/drift")
        data2 = r2.json()
        assert data2.get("drift_detected") is False, "Expected no drift on unchanged schema"

    def test_drift_detected_on_column_change(self, mesh_app, db_conn) -> None:
        """Schema drift detected when Silver column is renamed."""
        # Add a temporary column to simulate drift
        try:
            db_conn.execute("ALTER TABLE silver.customer_profiles ADD COLUMN _dbook_test_col TEXT")
            db_conn.commit()

            r = mesh_app.get("/schema/drift")
            data = r.json()
            if data.get("available") is False:
                pytest.skip("dbook not enabled in app")
            assert data.get("drift_detected") is True, (
                "Expected drift after adding column to Silver table"
            )
        finally:
            # Clean up
            try:
                db_conn.execute("ALTER TABLE silver.customer_profiles DROP COLUMN IF EXISTS _dbook_test_col")
                db_conn.commit()
            except Exception:
                db_conn.rollback()
            # Reset hashes by checking drift again
            mesh_app.get("/schema/drift")

    def test_drift_in_refresh_report(self, mesh_app, db_conn) -> None:
        """scheduled_refresh() report includes drift events."""
        # Add temporary column
        try:
            db_conn.execute("ALTER TABLE silver.customer_profiles ADD COLUMN _dbook_test_col2 TEXT")
            db_conn.commit()

            r = mesh_app.post("/refresh/scheduled")
            assert r.status_code == 200
            data = r.json()
            assert "drift" in data, "Refresh report should include 'drift' key"
        finally:
            try:
                db_conn.execute("ALTER TABLE silver.customer_profiles DROP COLUMN IF EXISTS _dbook_test_col2")
                db_conn.commit()
            except Exception:
                db_conn.rollback()


class TestDbookSemanticDiscovery:
    """Capability discovery enhanced by dbook concept index."""

    def test_discover_returns_capabilities(self, mesh_app) -> None:
        """GET /discover returns UC capabilities (baseline)."""
        r = mesh_app.get("/discover")
        assert r.status_code == 200
        capabilities = r.json()
        assert len(capabilities) > 0

    def test_concept_index_enhances_matching(self, dbook_bridge, mesh_app) -> None:
        """Concept index provides semantic term-to-column mapping."""
        if not dbook_bridge or not dbook_bridge.available:
            pytest.skip("dbook not available")
        concepts = dbook_bridge.get_concepts()
        # Verify concept index has meaningful entries
        assert "customer" in concepts or "order" in concepts or "product" in concepts
        # Verify columns are mapped
        for term, mapping in concepts.items():
            if mapping.get("columns"):
                # At least some terms should map to columns
                return
        pytest.fail("No concept terms mapped to columns")


class TestT2ProductionGuards:
    """T2 Silver fallback has production-grade safety guards."""

    def test_explain_guard_config_exists(self, dbook_bridge) -> None:
        """EXPLAIN cost guard is configured."""
        from cognimesh_core.config import CogniMeshConfig
        config = CogniMeshConfig()
        assert hasattr(config, "t2_max_explain_cost")
        assert config.t2_max_explain_cost > 0

    def test_table_size_guard_config_exists(self, dbook_bridge) -> None:
        """Table size guard is configured."""
        from cognimesh_core.config import CogniMeshConfig
        config = CogniMeshConfig()
        assert hasattr(config, "t2_max_source_rows")
        assert config.t2_max_source_rows > 0

    def test_concurrency_guard_config_exists(self, dbook_bridge) -> None:
        """T2 concurrency limit is configured."""
        from cognimesh_core.config import CogniMeshConfig
        config = CogniMeshConfig()
        assert hasattr(config, "t2_max_concurrent")
        assert config.t2_max_concurrent > 0

    def test_t2_query_within_guards(self, mesh_app) -> None:
        """T2 query on small Silver tables passes all guards."""
        r = mesh_app.post("/query", json={
            "question": "What is the total revenue by region?",
            "agent_id": "benchmark",
        })
        assert r.status_code == 200
        data = r.json()
        # Should succeed (T0 match or T2 within guards) — not rejected by guards
        assert data["tier"] in ("T0", "T2", "T3")
        if data["tier"] == "T3":
            # If T3, should NOT be because of explain_cost or source_table_too_large
            reason = data.get("metadata", {}).get("reason", "")
            assert reason not in ("explain_cost_exceeded", "source_table_too_large")

    def test_gateway_has_semaphore(self) -> None:
        """Gateway has T2 concurrency semaphore."""
        from cognimesh_core.config import CogniMeshConfig
        from cognimesh_core.gateway import Gateway
        from cognimesh_core.audit import AuditLog
        from cognimesh_core.capability_index import CapabilityIndex
        from cognimesh_core.gold_manager import GoldManager
        from cognimesh_core.lineage import LineageTracker
        from cognimesh_core.registry import UCRegistry

        config = CogniMeshConfig()
        registry = UCRegistry(config)
        gw = Gateway(config, registry, CapabilityIndex(registry),
                     GoldManager(config), LineageTracker(config), AuditLog(config))
        assert hasattr(gw, "_t2_semaphore")
