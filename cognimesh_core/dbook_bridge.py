"""Bridge between CogniMesh and dbook for rich schema introspection.

All dbook imports are deferred (inside methods / try-except) so that dbook
remains an optional dependency.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.models import DriftEvent

logger = logging.getLogger(__name__)


def _convert_url(url: str) -> str:
    """Convert a psycopg3-style URL to a psycopg2-style URL for SQLAlchemy."""
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


class DbookBridge:
    """Bridge between CogniMesh and dbook for rich schema introspection."""

    def __init__(self, config: CogniMeshConfig) -> None:
        self._config: CogniMeshConfig = config
        self._catalog: Any = None  # SQLAlchemyCatalog or None
        self._book: Any = None  # BookMeta or None
        self._concepts: dict = {}  # term -> {tables, columns, aliases}
        self._hashes: dict[str, str] = {}  # table_name -> SHA256 hex
        self._available: bool = False
        self._last_introspected: datetime | None = None

        if not config.dbook_enabled:
            logger.info("dbook integration disabled via config")
            return

        sa_url = _convert_url(config.database_url)

        try:
            from dbook.catalog import SQLAlchemyCatalog  # type: ignore[import-untyped]

            self._catalog = SQLAlchemyCatalog(sa_url)
            self._available = True
            logger.info("dbook bridge initialised (url=%s)", sa_url.split("@")[-1])
        except ImportError:
            logger.warning(
                "dbook is not installed — rich introspection unavailable. "
                "Install with: pip install dbook"
            )
        except Exception:
            logger.exception("Failed to create dbook SQLAlchemyCatalog")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether dbook is installed and catalog was created."""
        return self._available

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def introspect(self) -> Any:
        """Run full introspection on Silver schema.  Cache results.

        Calls ``catalog.introspect_all`` then generates concepts and computes
        per-table hashes.

        Returns:
            BookMeta or None if dbook is unavailable.
        """
        if not self._available:
            return None

        try:
            from dbook.hasher import compute_table_hash  # type: ignore[import-untyped]
            from dbook.generators.concepts import generate_concepts  # type: ignore[import-untyped]
        except ImportError:
            logger.error("dbook modules missing despite catalog being available")
            self._available = False
            return None

        t0 = time.perf_counter()

        try:
            book = self._catalog.introspect_all(
                schemas=[self._config.silver_schema],
                include_sample_data=True,
                sample_limit=self._config.dbook_sample_rows,
                include_row_count=self._config.dbook_include_row_count,
            )
        except Exception:
            logger.exception("dbook introspection failed")
            return None

        # Compute per-table hashes
        hashes: dict[str, str] = {}
        schema_meta = book.schemas.get(self._config.silver_schema)
        if schema_meta is not None:
            for table_name, table_meta in schema_meta.tables.items():
                hashes[table_name] = compute_table_hash(table_meta)

        # Generate concept index
        concepts = generate_concepts(book)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "dbook introspection completed in %.1fms (%d tables, %d concepts)",
            elapsed_ms,
            len(hashes),
            len(concepts),
        )

        # Cache everything
        self._book = book
        self._hashes = hashes
        self._concepts = concepts
        self._last_introspected = datetime.now(timezone.utc)

        return book

    # ------------------------------------------------------------------
    # Cached accessors
    # ------------------------------------------------------------------

    def get_book(self) -> Any:
        """Return cached BookMeta from last introspection."""
        return self._book

    def get_concepts(self) -> dict:
        """Return cached concepts index from last introspection."""
        return self._concepts

    def get_table_metadata_rich(self) -> dict:
        """Return flattened dict of table_name -> TableMeta from cached book.

        Iterates ``book.schemas[silver_schema].tables`` and returns the dict.
        Returns empty dict if not available.
        """
        if self._book is None:
            return {}

        schema_meta = self._book.schemas.get(self._config.silver_schema)
        if schema_meta is None:
            return {}

        return dict(schema_meta.tables)

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def check_drift(self) -> list[DriftEvent]:
        """Re-introspect and compare hashes.  Return list of DriftEvent.

        1. Re-run ``introspect_all`` (fresh from DB).
        2. For each table, compute new hash.
        3. Compare against stored ``self._hashes``.
        4. If different: create ``DriftEvent`` with old_hash, new_hash,
           detected_at=now.
        5. Update stored hashes to new values.
        6. Update cached book and concepts.
        7. Return list of ``DriftEvent`` objects.

        Handles added tables (old_hash="") and removed tables (new_hash="").
        """
        if not self._available:
            return []

        try:
            from dbook.hasher import compute_table_hash  # type: ignore[import-untyped]
            from dbook.generators.concepts import generate_concepts  # type: ignore[import-untyped]
        except ImportError:
            logger.error("dbook modules missing during drift check")
            self._available = False
            return []

        old_hashes = dict(self._hashes)

        # Clear cached metadata so the inspector picks up schema changes
        if hasattr(self._catalog, "clear_cache"):
            self._catalog.clear_cache()

        # Fresh introspection
        t0 = time.perf_counter()
        try:
            book = self._catalog.introspect_all(
                schemas=[self._config.silver_schema],
                include_sample_data=True,
                sample_limit=self._config.dbook_sample_rows,
                include_row_count=self._config.dbook_include_row_count,
            )
        except Exception:
            logger.exception("dbook introspection failed during drift check")
            return []

        # Compute new hashes
        new_hashes: dict[str, str] = {}
        schema_meta = book.schemas.get(self._config.silver_schema)
        if schema_meta is not None:
            for table_name, table_meta in schema_meta.tables.items():
                new_hashes[table_name] = compute_table_hash(table_meta)

        # Regenerate concepts
        concepts = generate_concepts(book)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "dbook introspection completed in %.1fms (%d tables, %d concepts)",
            elapsed_ms,
            len(new_hashes),
            len(concepts),
        )

        now = datetime.now(timezone.utc)
        drift_events: list[DriftEvent] = []

        # All table names from both old and new
        all_tables = set(old_hashes) | set(new_hashes)

        for table_name in sorted(all_tables):
            old_h = old_hashes.get(table_name, "")
            new_h = new_hashes.get(table_name, "")

            if old_h != new_h:
                drift_events.append(
                    DriftEvent(
                        table_name=table_name,
                        old_hash=old_h,
                        new_hash=new_h,
                        detected_at=now,
                        affected_gold_views=[],
                    )
                )

        if drift_events:
            logger.info(
                "Schema drift detected: %d table(s) changed",
                len(drift_events),
            )
        else:
            logger.debug("No schema drift detected")

        # Update caches
        self._hashes = new_hashes
        self._book = book
        self._concepts = concepts
        self._last_introspected = now

        return drift_events

    def re_introspect(self) -> list[DriftEvent]:
        """Alias for check_drift that also ensures concepts are refreshed."""
        return self.check_drift()
