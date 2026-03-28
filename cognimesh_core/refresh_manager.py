"""Smart Gold view refresh manager.

Three refresh strategies:
1. TTL-based: check Gold views, refresh any past their TTL
2. Silver change detection: Postgres LISTEN/NOTIFY on Silver table changes
3. On-demand: explicit refresh triggered by API call

Key advantage over REST: CogniMesh knows WHICH Gold views depend on WHICH Silver
tables (via lineage). When Silver changes, only affected Gold views are refreshed.
REST would have to refresh everything or maintain manual dependency lists.
"""
from __future__ import annotations

import logging
import threading

import psycopg  # type: ignore[import-untyped]
from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.gold_manager import GoldManager
from cognimesh_core.models import UseCase
from cognimesh_core.registry import UCRegistry

logger = logging.getLogger(__name__)


class RefreshManager:
    """Manages Gold view refresh based on TTL, Silver changes, and on-demand triggers."""

    def __init__(
        self,
        config: CogniMeshConfig,
        gold_manager: GoldManager,
        registry: UCRegistry,
    ):
        self.config = config
        self.gold_manager = gold_manager
        self.registry = registry
        self._listener_thread: threading.Thread | None = None
        self._listener_stop = threading.Event()

    # ------------------------------------------------------------------
    # TTL-based refresh
    # ------------------------------------------------------------------

    def check_and_refresh_stale(self) -> dict[str, int]:
        """Check all Gold views. Refresh any that are past their TTL.

        Returns: {gold_view_name: rows_refreshed} for views that were refreshed.
        Only refreshes each view ONCE even if multiple UCs share it.
        """
        refreshed: dict[str, int] = {}
        seen_views: set[str] = set()

        for uc in self.registry.list_active():
            if not uc.gold_view or uc.gold_view in seen_views:
                continue
            seen_views.add(uc.gold_view)

            freshness = self.gold_manager.get_freshness(uc.gold_view)
            if freshness.is_stale:
                logger.info(
                    "Refreshing stale view %s (age: %.0fs, ttl: %ds)",
                    uc.gold_view,
                    freshness.age_seconds,
                    freshness.ttl_seconds,
                )
                try:
                    rows = self.gold_manager.refresh_gold(uc)
                    refreshed[uc.gold_view] = rows
                except Exception:
                    logger.exception("Failed to refresh %s", uc.gold_view)

        if not refreshed:
            logger.info("All Gold views are fresh — nothing to refresh")

        return refreshed

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def get_refresh_status(self) -> list[dict]:
        """Get current freshness status of all Gold views.

        Returns a list of dicts with view name, age, TTL, staleness, and served UCs.
        """
        status: list[dict] = []
        seen_views: set[str] = set()
        all_ucs = self.registry.list_active()

        for uc in all_ucs:
            if not uc.gold_view or uc.gold_view in seen_views:
                continue
            seen_views.add(uc.gold_view)

            freshness = self.gold_manager.get_freshness(uc.gold_view)
            served_ucs = [u.id for u in all_ucs if u.gold_view == uc.gold_view]

            status.append({
                "gold_view": uc.gold_view,
                "last_refreshed_at": (
                    freshness.last_refreshed_at.isoformat()
                    if freshness.last_refreshed_at
                    else None
                ),
                "age_seconds": round(freshness.age_seconds, 1),
                "ttl_seconds": freshness.ttl_seconds,
                "is_stale": freshness.is_stale,
                "serves_ucs": served_ucs,
                "uc_count": len(served_ucs),
            })

        return status

    def get_refresh_plan(self) -> list[dict]:
        """Preview what WOULD be refreshed without doing it.

        Returns list of Gold views that are stale and need refresh,
        with their dependencies and affected UCs.
        """
        plan: list[dict] = []
        seen_views: set[str] = set()
        all_ucs = self.registry.list_active()

        for uc in all_ucs:
            if not uc.gold_view or uc.gold_view in seen_views:
                continue
            seen_views.add(uc.gold_view)

            freshness = self.gold_manager.get_freshness(uc.gold_view)
            if freshness.is_stale:
                served_ucs = [u.id for u in all_ucs if u.gold_view == uc.gold_view]
                plan.append({
                    "gold_view": uc.gold_view,
                    "age_seconds": round(freshness.age_seconds, 1),
                    "ttl_seconds": freshness.ttl_seconds,
                    "source_tables": uc.source_tables or [],
                    "affected_ucs": served_ucs,
                    "action": "refresh",
                })

        return plan

    # ------------------------------------------------------------------
    # Silver change detection (event-driven refresh)
    # ------------------------------------------------------------------

    def on_silver_change(self, silver_table: str) -> dict[str, int]:
        """Handle a Silver table change. Find affected Gold views via lineage, refresh them.

        This is the key advantage: CogniMesh knows which Gold views depend on which
        Silver tables. Only the affected views are refreshed, not all of them.

        REST equivalent: refresh everything, or maintain a manual dependency map.
        """
        # Find Gold views that source from this Silver table
        affected_views: set[str] = set()
        view_to_uc: dict[str, UseCase] = {}

        for uc in self.registry.list_active():
            if uc.source_tables and silver_table in uc.source_tables and uc.gold_view:
                affected_views.add(uc.gold_view)
                if uc.gold_view not in view_to_uc:
                    view_to_uc[uc.gold_view] = uc

        if not affected_views:
            logger.info(
                "No Gold views depend on %s — nothing to refresh", silver_table
            )
            return {}

        logger.info(
            "Silver table %s changed — refreshing %d affected Gold view(s): %s",
            silver_table,
            len(affected_views),
            ", ".join(sorted(affected_views)),
        )

        refreshed: dict[str, int] = {}
        for view in affected_views:
            uc = view_to_uc[view]
            try:
                rows = self.gold_manager.refresh_gold(uc)
                refreshed[view] = rows
                logger.info("  Refreshed %s: %d rows", view, rows)
            except Exception:
                logger.exception("  Failed to refresh %s", view)

        return refreshed

    # ------------------------------------------------------------------
    # Postgres LISTEN/NOTIFY listener
    # ------------------------------------------------------------------

    def start_listener(self) -> None:
        """Start listening for Silver table changes via Postgres LISTEN/NOTIFY.

        Runs in a background daemon thread. When a notification arrives on the
        'silver_changes' channel, calls on_silver_change() for the affected table.
        """
        if self._listener_thread and self._listener_thread.is_alive():
            logger.warning("Listener already running")
            return

        self._listener_stop.clear()
        self._listener_thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="cognimesh-refresh-listener",
        )
        self._listener_thread.start()
        logger.info("Started Silver change listener on 'silver_changes' channel")

    def stop_listener(self) -> None:
        """Stop the LISTEN thread."""
        self._listener_stop.set()
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
            self._listener_thread = None
        logger.info("Stopped Silver change listener")

    @property
    def is_listening(self) -> bool:
        """Check if the listener thread is running."""
        return self._listener_thread is not None and self._listener_thread.is_alive()

    def _listen_loop(self) -> None:
        """Background thread: LISTEN on Postgres, dispatch on_silver_change.

        Uses psycopg3's ``conn.notifies(timeout=...)`` generator which yields
        ``Notify`` objects.  A 1-second timeout lets us check the stop event
        regularly so the thread can be shut down cleanly.
        """
        conn = psycopg.connect(
            self.config.database_url,
            autocommit=True,
        )
        try:
            conn.execute("LISTEN silver_changes")
            logger.info("Listening on 'silver_changes' channel...")

            while not self._listener_stop.is_set():
                # conn.notifies(timeout=N) yields Notify objects that arrive
                # within the timeout window, then the generator exhausts.
                # Re-enter the loop to check the stop flag and listen again.
                gen = conn.notifies(timeout=1.0)
                for notify in gen:
                    silver_table = notify.payload
                    logger.info(
                        "Received change notification for: %s", silver_table
                    )
                    try:
                        self.on_silver_change(silver_table)
                    except Exception:
                        logger.exception(
                            "Error handling change for %s", silver_table
                        )
                    # Check stop flag between notifications
                    if self._listener_stop.is_set():
                        break

        except Exception:
            if not self._listener_stop.is_set():
                logger.exception("Listener thread error")
        finally:
            conn.close()
