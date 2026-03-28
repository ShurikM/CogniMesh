# CogniMesh

**An intelligent data mesh layer between AI agents and structured data platforms.**

Teams register Use Cases (business questions agents need answered). CogniMesh derives optimal Gold views, exposes them via MCP, tracks lineage, monitors freshness, logs every query, and handles unsupported questions gracefully — all from day one.

> REST API gives you a fast pipe. CogniMesh gives you a **governed, observable, self-documenting data serving platform**.

---

## Benchmark: REST API vs CogniMesh

We built **two complete implementations** serving the same 20 business questions from the same Postgres database (10K customers, 500 products, 200K orders). Then we measured everything.

### Key Results

| Dimension | REST API | CogniMesh | Winner |
|-----------|----------|-----------|--------|
| Raw query latency | 2.57 ms | 4.22 ms | REST (+2ms faster) |
| System properties (11 checks) | **0 / 11** | **11 / 11** | CogniMesh |
| Schema drift handling | SQL Error (500) | Isolated (serves from Gold) | CogniMesh |
| Unsupported question | 404 Not Found | Composes query from metadata | CogniMesh |
| Freshness awareness | None | Built-in (is_stale flag) | CogniMesh |
| Dependency intelligence | None | Full graph + impact analysis | CogniMesh |
| Smart refresh | Cron (all tables) | Only affected views | CogniMesh |
| Gold tables at 20 UCs | 20 tables | 7 views (65% fewer) | CogniMesh |
| Cost to add new use case | 4 files, 78 lines | 1 JSON, 12 lines (15%) | CogniMesh |
| Initial setup simplicity | 286 lines | 1,952 lines | REST |

### The 11-Property Scorecard

| Property | REST | CogniMesh |
|----------|:----:|:---------:|
| Discovery (agent asks "what can you answer?") | No | **Yes** |
| Lineage (trace result to source columns) | No | **Yes** |
| Audit Trail (every query logged) | No | **Yes** |
| Cost Attribution (per-UC cost tracking) | No | **Yes** |
| Change Governance (UC changes logged) | No | **Yes** |
| Freshness Awareness (stale data flagged) | No | **Yes** |
| Tiered Fallback (unsupported → T2/T3) | 404 | **Yes** |
| Schema Drift Detection (Silver changes) | 500 | **Yes** |
| Impact Analysis (what breaks if Silver changes?) | No | **Yes** |
| Provenance (trace Gold column to Silver source) | No | **Yes** |
| Smart Refresh (refresh only affected views) | No | **Yes** |

### Documents

| Document | What It Contains |
|----------|-----------------|
| **[Visual Benchmark Report](https://shurikm.github.io/CogniMesh/benchmark/results/report.html)** | Full HTML report with charts, scorecards, request flow diagrams, resilience scenarios, and marginal cost projections. **Start here.** |
| [Benchmark Report (Markdown)](benchmark/results/report.md) | Same content in plain markdown — 19 sections covering glossary, dataset, use cases, request flows, latency analysis, all 11 properties explained, resilience scenarios, code metrics, dependency intelligence, and honest REST advantages. |
| [Raw Results (JSON)](benchmark/results/results.json) | Machine-readable metrics: code counts by file type, marginal cost ratios. |
| **[Design Document](https://shurikm.github.io/CogniMesh/cognimesh.html)** | Full CogniMesh architecture, comparison tables, tier system, observability, product phases. |
| [Session Handover](cognimesh_handover.md) | Design decisions, measurement framework, day-one comparison analysis. |

---

## Run the Benchmark Yourself

### Prerequisites
- Docker (for Postgres)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Quick Start

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

### Step by Step

```bash
# 1. Start Postgres (creates schemas automatically)
make up

# 2. Seed Bronze/Silver/Gold data (10K customers, 200K orders)
make seed

# 3. Register CogniMesh UCs + derive Gold views
make setup-cognimesh

# 4. Run all 71 benchmark tests
make bench

# 5. Generate the report
make report
```

### What `make bench` Runs

| Test Suite | Tests | What It Measures |
|------------|-------|-----------------|
| `test_performance.py` | 6 | T0 latency per UC, both approaches (pytest-benchmark) |
| `test_throughput.py` | 8 | Concurrent request throughput at 1/5/10/25 users |
| `test_properties.py` | 16 | 11 binary assertions x 2 approaches (the scorecard) |
| `test_resilience_schema_drift.py` | 2 | Rename Silver column, observe both approaches |
| `test_resilience_unsupported_uc.py` | 2 | Ask unsupported question, compare REST 404 vs CogniMesh T2 |
| `test_resilience_staleness.py` | 2 | Expire TTL, check freshness metadata |
| `test_marginal_cost.py` | 5 | UC-04 file count + LOC comparison |
| `test_scale_benchmark.py` | 16 | Latency at scale + infrastructure metrics (storage, table count) |
| `test_refresh_and_deps.py` | 14 | Dependency graph, impact analysis, smart refresh |
| **Total** | **71** | **All pass** |

---

## Project Structure

```
CogniMesh/
├── cognimesh.html              # Design document (full architecture)
├── cognimesh_handover.md       # Session handover + design decisions
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
│   └── refresh_manager.py      #   Smart refresh (only affected Gold views)
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
│   ├── tests/                  # All benchmark tests (71 total)
│   │   ├── test_performance.py
│   │   ├── test_throughput.py
│   │   ├── test_properties.py  #   ← The 11/11 scorecard
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
│       ├── report.html         #   ← Visual report with charts
│       ├── report.md           #   ← Detailed markdown report
│       └── results.json        #   ← Raw metrics
│
└── LICENSE                     # Apache 2.0
```

---

## How CogniMesh Works (in 30 seconds)

1. **Register a Use Case** — write a JSON file: "What is the health status of customer X?" + required fields + freshness TTL
2. **System derives Gold** — CogniMesh creates an optimized Gold table from Silver, registers column-level lineage, sets up freshness tracking, and builds the dependency graph
3. **Agent queries** — `POST /query {"question": "..."}` → Gateway matches UC → serves from Gold (T0) with lineage + freshness + audit
4. **Unsupported question?** — Gateway composes SQL from Silver metadata (T2) or explains why it can't (T3). No 404s.
5. **Schema changes?** — Gold layer isolates agents from Silver drift. System detects and flags changes.
6. **Dependency intelligence** — impact analysis shows which Gold views and UCs break if a Silver table changes. Provenance traces any Gold column back to its Silver source.
7. **Smart refresh** — when Silver data changes, only affected Gold views are refreshed (not all of them). At 20 UCs, this means refreshing 3 views instead of 20.

---

## CogniMesh API Endpoints

```
POST /query                  — Query with UC routing (T0/T2/T3)
GET  /discover               — List all capabilities
GET  /health                 — Health check

GET  /dependencies           — Full dependency graph (Silver → Gold → UCs)
GET  /dependencies/impact    — What breaks if a Silver table changes?
GET  /dependencies/provenance — Where does this Gold column come from?
GET  /dependencies/what-if   — Change impact estimation

GET  /refresh/status         — Freshness of all Gold views
POST /refresh/check          — Auto-refresh stale views
GET  /refresh/plan           — Preview what would be refreshed
```

---

## What's NOT in the Benchmark (Yet)

| Feature | Status | Why Skipped |
|---------|--------|-------------|
| MCP server | Planned | Benchmark measures architecture, not transport protocol |
| LLM-based UC routing | Planned | Benchmark uses deterministic keyword matching for reproducibility |
| SQLMesh integration | Planned | Benchmark uses template-based Gold derivation |
| Multi-agent load testing | Planned | Single-agent sufficient to prove the architecture |
| Production data volumes | Planned | 200K orders sufficient for latency comparison |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Data models | Pydantic v2 |
| API framework | FastAPI |
| Database | Postgres 15 (Docker) |
| DB driver | psycopg 3 + connection pool |
| Test framework | pytest + pytest-benchmark |
| Package manager | uv |
| LLM (production) | Pluggable: OpenAI / Anthropic / Ollama |
| MCP (production) | Official MCP Python SDK |

## License

Apache 2.0
