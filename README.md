# CogniMesh

An open-source Python library (Apache 2.0) that acts as an intelligent data mesh layer between AI agents and structured data platforms.

## What CogniMesh Does

Teams register **Use Cases** — questions agents need to answer. CogniMesh derives optimal Gold views via SQL Mesh, exposes them through MCP (Model Context Protocol), and evolves the Gold layer from actual usage patterns.

**Key capabilities:**
- Near-zero maintenance per new use case — declarative registration, SQL Mesh derives the rest
- Self-improving Gold layer — derived from actual agent usage patterns
- Tiered fallback — no hard failure for unsupported queries (T0 -> T1 -> T2 -> T3)
- Built-in observability, lineage, and governance from day one
- Scales with agent count without linear engineering cost

## Architecture

```
Agents (any LLM / framework)
    | MCP
    v
CogniMesh Gateway
    +-- Capability Index (UC -> Gold view map)
    +-- Embedded Agent (routes questions -> UCs -> Gold views)
    +-- Materialization Engine (suggests new views)
    +-- Observability (OpenTelemetry -> ClickHouse)
    |
    v
SQL Mesh Layer (consolidation, SQL gen, lineage)
    |
    v
Gold Layer (derived from UCs, not designed upfront)
    |
    v
Silver / Bronze (Spark, DuckDB, Delta, Iceberg, Postgres, Snowflake, BigQuery)
```

## Tech Stack

- **Models:** Pydantic v2
- **MCP:** Official MCP Python SDK
- **LLM:** Pluggable (OpenAI, Anthropic, Ollama)
- **SQL Mesh:** SQLMesh Python API
- **Observability:** OpenTelemetry -> ClickHouse (prod) / DuckDB (dev)
- **CLI:** Typer + Rich
- **Eval:** DeepEval
- **Packaging:** uv + pyproject.toml

## Benchmark: REST API vs CogniMesh

Same Bronze/Silver data in Postgres. Same 3 use cases. Two approaches. Measured across 4 categories.

### Quick Start

```bash
git clone https://github.com/ShurikM/CogniMesh.git
cd CogniMesh
uv sync --all-extras
make all
```

### What's Measured

| Category | What | How |
|----------|------|-----|
| **Performance** | T0 latency, throughput | pytest-benchmark, async load test |
| **Developer Effort** | LOC, files, marginal UC cost | Code metrics + UC-04 addition comparison |
| **Resilience** | Schema drift, unsupported UC, staleness | 3 runnable scenario tests |
| **System Properties** | 8 binary assertions | The Scorecard (REST: 0/8, CogniMesh: 8/8) |

### The 8-Property Scorecard

| Property | REST | CogniMesh |
|----------|------|-----------|
| Discovery | No | Yes |
| Lineage | No | Yes |
| Audit Trail | No | Yes |
| Cost Attribution | No | Yes |
| Change Governance | No | Yes |
| Freshness Awareness | No | Yes |
| Tiered Fallback | 404 | T2/T3 |
| Schema Drift Detection | 500 | Isolated |

### Project Structure

```
benchmark/
  data/           # Postgres schema + seed data (10K customers, 200K orders)
  rest_api/       # Approach A: FastAPI + dedicated Gold tables
  cognimesh_app/  # Approach B: UC registration + CogniMesh gateway
  tests/          # All benchmark tests
  uc04/           # Marginal cost demo (REST: 4 files vs CogniMesh: 1 JSON)
  harness/        # Report generator
```

## Documentation

- **[Design Document](cognimesh.html)** — Full architecture, comparison, design decisions
- **[Session Handover](cognimesh_handover.md)** — Context for continuing development

## Status

Design phase complete. Benchmark project scaffolded with both implementations. Run `make all` to execute.

## License

Apache 2.0
