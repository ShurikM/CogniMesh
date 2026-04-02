"""GET /api/v1/freshness — Model freshness from dbt run results."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter  # type: ignore[import-untyped]

router = APIRouter(prefix="/api/v1", tags=["freshness"])

_RUN_RESULTS_PATH = Path(__file__).parent.parent / "dbt_artifacts" / "run_results.json"
_results: dict | None = None


def _load_results() -> dict:
    global _results
    if _results is not None:
        return _results
    with open(_RUN_RESULTS_PATH) as f:
        data: dict = json.load(f)
    _results = data
    return data


@router.get("/freshness")
def get_freshness() -> list[dict]:
    """Return freshness info for all dbt models."""
    results = _load_results()
    now = datetime.now(timezone.utc)

    freshness_list = []
    for result in results.get("results", []):
        model_name = result["unique_id"].split(".")[-1]
        timing = result.get("timing", [{}])
        completed_str = timing[0].get("completed_at", "") if timing else ""

        try:
            completed = datetime.fromisoformat(completed_str.replace("Z", "+00:00"))
            age_seconds = (now - completed).total_seconds()
        except (ValueError, TypeError):
            age_seconds = None

        freshness_list.append({
            "model": model_name,
            "status": result.get("status", "unknown"),
            "last_run_at": completed_str,
            "age_seconds": age_seconds,
            "execution_time_s": result.get("execution_time"),
            "rows_affected": result.get("rows_affected"),
        })

    return freshness_list
