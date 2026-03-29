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

    # Refresh
    refresh_mode: str = "scheduled"  # scheduled | realtime
    refresh_schedule: str = "0 */4 * * *"  # cron expression: every 4 hours (for documentation)

    # Gateway
    default_agent_id: str = "benchmark"

    model_config = {"env_prefix": "COGNIMESH_"}
