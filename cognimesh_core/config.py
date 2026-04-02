"""CogniMesh configuration — loaded from environment variables."""

from pydantic_settings import BaseSettings  # type: ignore[import-untyped]


class CogniMeshConfig(BaseSettings):
    """All configuration for CogniMesh. Env vars prefixed with COGNIMESH_."""

    database_url: str = "postgresql://cognimesh:cognimesh@localhost:5432/cognimesh_bench"
    gold_schema: str = "gold_cognimesh"
    silver_schema: str = "silver"
    internal_schema: str = "cognimesh_internal"

    # T2 guardrails
    t2_max_rows: int = 10_000
    t2_max_seconds: float = 5.0
    t2_max_cost_units: float = 100.0

    # T2 production guards
    t2_max_explain_cost: float = 50_000.0  # Postgres EXPLAIN cost units
    t2_max_source_rows: int = 10_000_000   # Max rows in source Silver table
    t2_max_concurrent: int = 3             # Max concurrent T2 queries

    # Refresh
    refresh_mode: str = "scheduled"  # scheduled | realtime
    refresh_schedule: str = "0 0 * * *"  # cron expression: daily at midnight

    # Gateway
    default_agent_id: str = "benchmark"

    # dbook integration
    dbook_enabled: bool = True
    dbook_sample_rows: int = 5
    dbook_include_row_count: bool = True

    model_config = {"env_prefix": "COGNIMESH_"}
