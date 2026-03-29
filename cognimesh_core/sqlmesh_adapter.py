"""Bridge between CogniMesh UC definitions and SQLMesh models.

Provides:
- Initialize SQLMesh context
- Run materialization for specific models
- Read lineage from SQLMesh
- Read freshness/audit from SQLMesh state
"""
from __future__ import annotations

import logging
from pathlib import Path

from cognimesh_core.config import CogniMeshConfig

logger = logging.getLogger(__name__)

SQLMESH_PROJECT_DIR = Path(__file__).parent / "sqlmesh_project"


class SQLMeshAdapter:
    """Adapter for SQLMesh operations."""

    def __init__(self, config: CogniMeshConfig):
        self.config = config
        self.project_dir = SQLMESH_PROJECT_DIR
        self._context = None

    def get_context(self):
        """Get or create SQLMesh context."""
        if self._context is None:
            try:
                import sqlmesh  # type: ignore[import-untyped]

                self._context = sqlmesh.Context(
                    paths=[str(self.project_dir)],
                    gateway="local",
                )
            except ImportError:
                logger.warning("sqlmesh not installed -- falling back to direct SQL")
                return None
            except Exception:
                logger.exception("Failed to create SQLMesh context")
                return None
        return self._context

    def run(self, model_name: str | None = None) -> bool:
        """Run SQLMesh plan + apply for materialization.

        If *model_name* is provided, only that model (and its upstream
        dependencies) will be selected.  Otherwise all models are
        materialized.

        Returns True on success, False on failure.
        """
        ctx = self.get_context()
        if ctx is None:
            return False

        try:
            # plan() with auto_apply=True generates and applies in one shot.
            # no_prompts=True avoids interactive confirmation.
            ctx.plan(
                select_models=[model_name] if model_name else None,
                auto_apply=True,
                no_prompts=True,
            )
            return True
        except Exception:
            logger.exception("SQLMesh run failed for %s", model_name or "all")
            return False

    def plan(self, model_name: str | None = None):
        """Generate a SQLMesh plan (dry run -- shows what would change)."""
        ctx = self.get_context()
        if ctx is None:
            return None

        try:
            return ctx.plan(
                select_models=[model_name] if model_name else None,
                auto_apply=False,
                no_prompts=True,
            )
        except Exception:
            logger.exception("SQLMesh plan failed")
            return None

    def get_lineage(self, model_name: str) -> dict:
        """Get DAG lineage from SQLMesh for a model."""
        ctx = self.get_context()
        if ctx is None:
            return {}

        try:
            lineage = ctx.get_dag(select_models=[model_name])
            return lineage
        except Exception:
            logger.exception("Failed to get lineage for %s", model_name)
            return {}

    def is_available(self) -> bool:
        """Check if SQLMesh is installed and configured."""
        return self.get_context() is not None
