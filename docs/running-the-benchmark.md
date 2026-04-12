# Running the Benchmark

> Back to [README](../README.md)

## Prerequisites

- Docker (for Postgres)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

## Quick Start

```bash
git clone https://github.com/ShurikM/CogniMesh.git
cd CogniMesh

# Install dependencies
uv sync --all-extras

# Start Postgres, seed data, run all tests, generate report
make all

# View the visual report
open benchmark/results/report.html
```

## Step by Step

### 1. Start Postgres

Creates schemas automatically.

```bash
make up
```

### 2. Seed Bronze/Silver/Gold Data

10K customers, 200K orders.

```bash
make seed
```

### 3. Register CogniMesh UCs and Derive Gold Views

```bash
make setup-cognimesh
```

### 4. Run All 90 Benchmark Tests

```bash
make bench
```

### 5. Generate the Report

```bash
make report
```

## What `make bench` Runs

| Test Suite | Tests | What It Measures |
|------------|-------|-----------------|
| `test_performance.py` | 6 | T0 latency per UC, both approaches (pytest-benchmark) |
| `test_throughput.py` | 8 | Concurrent request throughput at 1/5/10/25 users |
| `test_properties.py` | 16 | 8 binary assertions x 2 approaches (the scorecard) |
| `test_resilience_schema_drift.py` | 2 | Rename Silver column, observe both approaches |
| `test_resilience_unsupported_uc.py` | 2 | Ask unsupported question, compare REST 404 vs CogniMesh T2 |
| `test_resilience_staleness.py` | 2 | Expire TTL, check freshness metadata |
| `test_marginal_cost.py` | 5 | UC-04 file count + LOC comparison |
| `test_scale_benchmark.py` | 16 | Latency at scale + infrastructure metrics (storage, table count) |
| `test_refresh_and_deps.py` | 14 | Dependency graph, impact analysis, smart refresh |
| `test_dbook_integration.py` | 19 | dbook introspection, concept index, SQL validation, drift detection, T2 production guards |
| **Total** | **90** | **All pass** |

## Project Structure

```
CogniMesh/
├── cognimesh.html              # Design document (full architecture)
├── docker-compose.yml          # Postgres 15 for benchmark
├── Makefile                    # One-command runner (make all)
├── pyproject.toml              # Python project config
│
├── cognimesh_core/             # Minimal CogniMesh library (11 modules)
│   ├── models.py               #   Pydantic v2 data models
│   ├── config.py               #   Configuration from env vars
│   ├── db.py                   #   Postgres connection pool
│   ├── registry.py             #   UC CRUD + change logging
│   ├── capability_index.py     #   UC discovery + keyword matching
│   ├── gateway.py              #   T0/T2/T3 query routing engine
│   ├── gold_manager.py         #   Gold table refresh + freshness
│   ├── lineage.py              #   Column-level lineage tracking
│   ├── audit.py                #   Audit log + cost attribution
│   ├── query_composer.py       #   T2 SQL composition from metadata
│   ├── dependency.py           #   Dependency graph + impact analysis + provenance
│   ├── refresh_manager.py      #   Scheduled + real-time refresh (only affected Gold views)
│   └── mcp_server.py           #   MCP server — 6 tools wrapping the Gateway
│
├── benchmark/
│   ├── data/
│   │   ├── schema.sql          #   Postgres DDL (5 schemas, 17 tables)
│   │   ├── seed.py             #   Deterministic data generator
│   │   ├── schema_scale.sql    #   DDL for 20-UC scale benchmark
│   │   ├── seed_scale.py       #   Data generator for scale benchmark
│   │   └── schema_triggers.sql #   Postgres triggers for change detection
│   │
│   ├── rest_api/               # Approach A: Traditional REST
│   │   ├── app.py              #   FastAPI app (3 endpoints)
│   │   ├── endpoints/          #   customer_health, top_products, at_risk
│   │   ├── models.py           #   Response models
│   │   └── gold_tables.sql     #   Hand-written Gold derivation SQL
│   │
│   ├── cognimesh_app/          # Approach B: CogniMesh
│   │   ├── app.py              #   Gateway wrapper (all API endpoints)
│   │   ├── setup.py            #   Register UCs + derive Gold + register lineage
│   │   └── use_cases/          #   20 UC JSON definitions (~12 lines each)
│   │
│   ├── tests/                  # All benchmark tests (90 total)
│   │   ├── test_performance.py
│   │   ├── test_throughput.py
│   │   ├── test_properties.py  #   ← The 8/8 vs 5/8 scorecard
│   │   ├── test_resilience_*.py
│   │   ├── test_marginal_cost.py
│   │   ├── test_scale_benchmark.py    # 20-UC scale + infra metrics
│   │   └── test_refresh_and_deps.py   # Dependency graph + smart refresh
│   │
│   ├── uc04/                   # Marginal cost demo
│   │   ├── rest_changes/       #   4 files, 78 SLOC (endpoint + Gold SQL + model + test)
│   │   └── cognimesh_changes/  #   1 file, 12 SLOC (JSON UC definition)
│   │
│   ├── harness/                # Report generation
│   │   ├── metrics.py
│   │   └── report.py
│   │
│   └── results/                # Generated output
│       └── report.html         #   ← Visual report with charts
│
└── LICENSE                     # Apache 2.0
```
