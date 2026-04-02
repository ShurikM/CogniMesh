"""GET /api/v1/lineage/{model} — Column lineage from dbt manifest."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException  # type: ignore[import-untyped]

router = APIRouter(prefix="/api/v1", tags=["lineage"])

_MANIFEST_PATH = Path(__file__).parent.parent / "dbt_artifacts" / "manifest.json"
_manifest: dict | None = None


def _load_manifest() -> dict:
    global _manifest
    if _manifest is not None:
        return _manifest
    with open(_MANIFEST_PATH) as f:
        data: dict = json.load(f)
    _manifest = data
    return data


@router.get("/lineage/{model_name}")
def get_lineage(model_name: str) -> dict:
    """Return column-level lineage for a dbt model."""
    manifest = _load_manifest()
    node_key = f"model.cognimesh_bench.{model_name}"
    node = manifest.get("nodes", {}).get(node_key)
    if not node:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found in manifest")

    lineage = []
    for col_name, col_info in node.get("columns", {}).items():
        meta = col_info.get("meta", {})
        if meta.get("source_table"):
            lineage.append({
                "gold_column": col_name,
                "source_table": meta["source_table"],
                "source_column": meta.get("source_column", col_name),
                "transformation": meta.get("transformation", "unknown"),
            })

    return {
        "model": model_name,
        "schema": node.get("schema", "gold_rest"),
        "lineage": lineage,
        "depends_on": node.get("depends_on", {}).get("nodes", []),
    }
