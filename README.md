# CogniMesh

An open-source Python library (Apache 2.0) that acts as an intelligent data mesh layer between AI agents and structured data platforms.

## What CogniMesh Does

Teams register **Use Cases** — questions agents need to answer. CogniMesh derives optimal Gold views via SQL Mesh, exposes them through MCP (Model Context Protocol), and evolves the Gold layer from actual usage patterns.

**Key capabilities:**
- Near-zero maintenance per new use case — declarative registration, SQL Mesh derives the rest
- Self-improving Gold layer — derived from actual agent usage patterns
- Tiered fallback — no hard failure for unsupported queries (T0 → T1 → T2 → T3)
- Built-in observability, lineage, and governance from day one
- Scales with agent count without linear engineering cost

## Architecture

```
Agents (any LLM / framework)
    │ MCP
    ▼
CogniMesh Gateway
    ├── Capability Index (UC → Gold view map)
    ├── Embedded Agent (routes questions → UCs → Gold views)
    ├── Materialization Engine (suggests new views)
    └── Observability (OpenTelemetry → ClickHouse)
    │
    ▼
SQL Mesh Layer (consolidation, SQL gen, lineage)
    │
    ▼
Gold Layer (derived from UCs, not designed upfront)
    │
    ▼
Silver / Bronze (Spark, DuckDB, Delta, Iceberg, Postgres, Snowflake, BigQuery)
```

## Documentation

- **[Design Document](cognimesh.html)** — Full architecture, comparison, design decisions, product phases
- **[Session Handover](cognimesh_handover.md)** — Context for continuing design and implementation

## Tech Stack

- **Models:** Pydantic v2
- **MCP:** Official MCP Python SDK
- **LLM:** Pluggable (OpenAI, Anthropic, Ollama)
- **SQL Mesh:** SQLMesh Python API
- **Observability:** OpenTelemetry → ClickHouse (prod) / DuckDB (dev)
- **CLI:** Typer + Rich
- **Eval:** DeepEval
- **Packaging:** uv + pyproject.toml

## Status

Currently in design phase. See the [design document](cognimesh.html) for full details.

## License

Apache 2.0
