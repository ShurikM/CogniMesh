# CogniMesh

<p align="center">
  <img src="docs/logo.svg" alt="CogniMesh Logo" width="96">
</p>

**An intelligent data mesh layer between AI agents and structured data platforms.**

Teams register Use Cases (business questions agents need answered). CogniMesh derives optimal Gold views, exposes them via REST API, tracks lineage, monitors freshness, logs every query, and handles unsupported questions gracefully — all from day one.

CogniMesh integrates with [dbook](https://github.com/ShurikM/dbook) for rich Silver schema intelligence — foreign keys, enums, sample data, column semantics — enabling SQL validation of composed queries, proactive schema drift detection via structural hashing, and a semantic concept index for enhanced UC discovery.

> REST API gives you a fast pipe. CogniMesh gives you a **governed, observable, self-documenting data serving platform**.

> **Project Status:** Core architecture proven and dbook integration complete — benchmark passes 90 tests (8/8 properties, 19 dbook integration tests including T2 production guards). Ready for production implementation when needed.

## Architecture

<p align="center">
  <img src="docs/architecture.svg" alt="CogniMesh Architecture" width="700">
</p>

CogniMesh is an intelligent serving layer for AI agents with two deployment modes:

### Mode 1: Connect (start here)
Connect to your existing Silver layer. CogniMesh introspects the schema, builds Gold views from UC definitions, and serves agents with lineage, observability, and access control. Your existing dbt/Spark/Airflow pipeline stays untouched.

### Mode 2: Manage (full platform)
CogniMesh + SQLMesh manages the entire Bronze→Silver→Gold pipeline. Full lineage from raw source to agent response. Complete schema knowledge across all layers. Intelligent refresh based on the full DAG.

### Migration path
Start with Mode 1 — zero disruption. Migrate Silver tables into SQLMesh models one at a time. Each migrated table gains full Bronze→Silver→Gold lineage. Eventually, CogniMesh has complete observation of all layers needed to support current and future UCs.

### Why Gold must be a serving database

Agents do individual lookups — "health of customer X", "orders for product Y." That needs sub-10ms latency. Open table formats (Iceberg/Delta) on object storage take 100-1000ms per lookup.

CogniMesh separates **transformation storage** from **serving storage**:
- **Bronze/Silver**: can live on a lakehouse (Iceberg, Delta, Spark) — cheap, batch-optimized
- **Gold**: must be a serving database — OLTP (Postgres, DuckDB, MongoDB) or OLAP (StarRocks, ClickHouse, Druid) — fast, agent-optimized

SQLMesh manages transformations across all layers. CogniMesh materializes Gold into the serving DB and serves agents from there.

### Engine configurations

**Single-engine** — All layers on one database (Postgres, StarRocks, DuckDB). SQLMesh manages Bronze→Silver→Gold in the same engine. Simple setup, ideal for small/medium teams or getting started.

**Multi-engine** — Silver on a lakehouse (Spark + Iceberg/Delta), Gold on a serving database (Postgres, StarRocks, ClickHouse). SQLMesh manages transformations on each engine natively. CogniMesh orchestrates cross-engine materialization — reads Silver from the lakehouse, materializes Gold into the serving DB. This is the enterprise configuration for teams with existing lakehouse infrastructure.

Both configurations get the same CogniMesh capabilities: UC registry, lineage, observability, smart refresh, dependency intelligence, security.

**Five pillars across both modes:**
- **Explainability** — Every response traces back to source data. Full lineage in Mode 2, Gold→Silver lineage in Mode 1.
- **Observability** — Every query logged: who asked, what it cost, how fresh the data is.
- **Self-service** — Register a UC with a 12-line JSON. System derives Gold, consolidates overlapping views. Scheduled refresh is the primary mode: check TTLs, rebuild only stale views, report what changed. Real-time mode (Postgres LISTEN/NOTIFY) available for UCs that need immediate freshness.
- **Flexibility** — Unknown questions composed from metadata (T2), not 404s. T2 patterns auto-promoted to Gold UCs.
- **Security** — Agent identity and scoping, per-UC access control, row-level data isolation.

---

## dbook Integration

CogniMesh integrates with [dbook](https://github.com/ShurikM/dbook) — a database metadata compiler that extracts schema intelligence for AI agent consumption. This replaces the shallow `information_schema.columns` introspection with rich structural metadata.

### What dbook Provides

| Capability | Before (vanilla) | After (with dbook) |
|---|---|---|
| **T2 Column Matching** | Fuzzy keyword match on column names | Concept-boosted scoring with IDF weighting |
| **T2 Row Estimation** | Heuristic defaults (1-50 rows) | Actual `row_count` from dbook introspection |
| **Enum Validation** | None — raw string matching | dbook detects enum-like columns, validates/corrects filter values |
| **SQL Validation** | Execute and catch errors | Pre-flight validation via SQLGlot (table/column/FK/enum checks) |
| **Schema Drift** | Detected reactively when Gold refresh fails | Proactive SHA256 hash comparison on every scheduled refresh |
| **PII Awareness** | None — no sensitivity detection | dbook scans column names + sample data via Presidio, marks sensitivity levels |
| **UC Discovery** | Keyword overlap scoring | Semantic concept index boosts matches for domain terms |

### How It Works

1. **Startup**: `DbookBridge` creates a read-only SQLAlchemy connection and runs `introspect_all(schemas=["silver"])` — capturing columns, FKs, enums, row counts, and sample data.
2. **Concept Index**: `generate_concepts(book)` builds a term→table/column mapping (e.g., "customer" → customer_profiles, orders.customer_id).
3. **Injection**: Rich metadata is injected into `TemplateComposer` and `CapabilityIndex` at startup.
4. **T2 Path**: Composed SQL is validated against the dbook schema before execution. Invalid queries are rejected to T3 with actionable suggestions. PII-marked columns (email, phone, SSN, credit card) are respected — T2 avoids selecting sensitive columns in ad-hoc results.
5. **Refresh Cycle**: `scheduled_refresh()` calls `check_drift()` — re-introspects Silver and compares SHA256 hashes. Drift events are logged with affected Gold views.

### Configuration

| Env Var | Default | Description |
|---|---|---|
| `COGNIMESH_DBOOK_ENABLED` | `true` | Enable/disable dbook integration |
| `COGNIMESH_DBOOK_SAMPLE_ROWS` | `5` | Sample rows per table during introspection |
| `COGNIMESH_DBOOK_INCLUDE_ROW_COUNT` | `true` | Include row counts (requires COUNT(*) query) |
| `COGNIMESH_T2_MAX_EXPLAIN_COST` | `50000` | Max Postgres EXPLAIN cost before T2 query is rejected |
| `COGNIMESH_T2_MAX_SOURCE_ROWS` | `10000000` | Max source table rows (from dbook) before T2 query is rejected |
| `COGNIMESH_T2_MAX_CONCURRENT` | `3` | Max concurrent T2 queries (semaphore) |

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/schema/drift` | GET | Check Silver schema for structural changes |

dbook is an **optional dependency** — CogniMesh runs without it, falling back to basic `information_schema` metadata.

All 19 dbook integration tests pass in the benchmark: schema-aware T2 composition uses rich metadata (FKs, enums, sample data), drift detection works proactively via SHA256 hash comparison on every scheduled refresh, semantic discovery via the concept index boosts UC matching for domain terms, and T2 production guards (EXPLAIN cost check, table size guard, concurrency semaphore) are verified.

### T2 Production Safety Guards

T2 Silver fallback composes SQL dynamically — which is powerful but dangerous without proper guards. CogniMesh implements three production-grade safety mechanisms:

| Guard | What it does | Config | Default |
|-------|-------------|--------|---------|
| **EXPLAIN cost check** | Runs `EXPLAIN (FORMAT JSON)` before execution. Rejects if Postgres cost estimate exceeds threshold. | `COGNIMESH_T2_MAX_EXPLAIN_COST` | 50,000 |
| **Table size guard** | Uses dbook's actual row counts to reject queries against Silver tables larger than threshold. | `COGNIMESH_T2_MAX_SOURCE_ROWS` | 10,000,000 |
| **Concurrency semaphore** | Limits concurrent T2 queries to prevent connection pool saturation. | `COGNIMESH_T2_MAX_CONCURRENT` | 3 |

These complement the existing guards (statement timeout, result row limit) to prevent catastrophically expensive queries on large Silver tables.

**T2 rejection flow:** If any guard triggers, the query is rejected to T3 with the specific reason (`explain_cost_exceeded`, `source_table_too_large`, `t2_concurrency_limit`) and actionable metadata (actual cost, row count, limits). The agent knows exactly why the query was rejected and what the limits are.

---

## Why Gold Still Matters (dbook + CogniMesh)

If dbook gives agents schema intelligence, doesn't that make the Gold layer unnecessary? No — Gold layers exist for two different reasons:

| Reason | Who solves it | Still needed? |
|---|---|---|
| "Consumers can't understand Silver" — don't know what tables exist, what columns mean, what values are valid | dbook | **No** — dbook gives agents this understanding |
| "Queries need to be fast, governed, audited" — sub-10ms response, access control, freshness tracking, approval workflows | CogniMesh T0 | **Yes** — can't get this from metadata alone |

**dbook eliminates Gold for understanding. CogniMesh keeps Gold for performance and governance.**

### Before dbook

- **T0 (Gold):** works great for known queries
- **T2 (Silver fallback):** weak — keyword matching, wrong SQL, low confidence
- **Result:** You MUST pre-build Gold views for almost every question. Miss a use case? Agent gets T3 rejection.

### After dbook

- **T0 (Gold):** same — fast, governed, audited for critical queries
- **T2 (Silver fallback):** STRONG — enum values, FK semantics, validated SQL
- **Result:** Only build Gold views for performance-critical queries. T2 handles the long tail of ad-hoc questions correctly. Fewer Gold views to maintain, better coverage.

### The combined pitch

> CogniMesh + dbook: Build Gold views for your top 20 critical queries (T0). Let dbook-powered T2 handle the other 80% of ad-hoc questions directly from Silver — correctly, with enum values, validated SQL, and PII awareness. No more "we don't have a Gold table for that."

### Claim refinement

| Claim | Accurate? |
|---|---|
| "No Gold needed for agent DISCOVERY" | Yes — dbook |
| "No Gold needed for agent UNDERSTANDING" | Yes — dbook |
| "No Gold needed for PERFORMANCE" | No — T0 Gold is still fastest |
| "No Gold needed for GOVERNANCE" | No — audit, access control, freshness need infrastructure |
| "FEWER Gold views needed" | Yes — T2 + dbook handles what used to require pre-built Gold |

dbook and CogniMesh are complementary, not contradictory. dbook shrinks the Gold layer from "everything must be pre-built" to "only performance-critical queries need Gold."

---

### Change Governance: How the Approval Queue Works

CogniMesh enforces a simple invariant: **nothing changes in Gold without human approval.** This is implemented as a DB-backed approval workflow, not a checkbox.

**Flow:**

```
Register/Update UC ──→ UC status: "pending_approval"
                              │
                              ▼
                    approval_queue table (status: "pending")
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              POST /approve        POST /reject
                    │                   │
                    ▼                   ▼
            UC activated           UC stays inactive
            Gold refreshed         No Gold changes
```

**API Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/approvals` | GET | List all pending approval requests |
| `/approvals/history` | GET | Approval history (filterable by UC, with limit) |
| `/approvals/{id}` | GET | Get details of a specific approval request |
| `/approvals/{id}/approve` | POST | Approve — activates UC + triggers Gold refresh |
| `/approvals/{id}/reject` | POST | Reject — UC stays inactive, Gold unchanged |

**Example: Approve a UC change**

```bash
# List pending approvals
curl -s localhost:8000/approvals | jq '.[].id'

# Review a specific approval
curl -s localhost:8000/approvals/1 | jq

# Approve it (triggers Gold refresh)
curl -X POST "localhost:8000/approvals/1/approve?reviewed_by=alice&note=LGTM"

# Or reject it
curl -X POST "localhost:8000/approvals/1/reject?reviewed_by=alice&reason=needs+schema+review"
```

**What gets stored** (in `cognimesh_internal.approval_queue`):

| Column | Description |
|--------|-------------|
| `uc_id` | Which UC is being changed |
| `action` | What's happening: `register`, `update`, `deactivate`, `refresh` |
| `status` | `pending` → `approved` or `rejected` |
| `request_data` | Full UC definition at time of submission (JSONB) |
| `requested_by` / `reviewed_by` | Who submitted / who approved |
| `reviewed_at` | When the decision was made |
| `review_note` | Optional comment explaining the decision |

**What this is NOT:**
- No UI (API-only — integrate with your existing review tooling)
- No Slack/email notifications (add a webhook in your deployment)
- No multi-stage approval (single approver, not a committee)

This is deliberately minimal. The goal is enforcing the invariant (no unreviewed Gold changes), not replacing your organization's review process. Wire the API into Slack, PagerDuty, or a custom dashboard as needed.

---

## Benchmark: dbt REST Stack vs CogniMesh

We built **two complete implementations** serving the same 20 business questions from the same Postgres database (10K customers, 500 products, 200K orders). Then we measured everything.

### Key Results

| Dimension | REST API | CogniMesh | Winner |
|-----------|----------|-----------|--------|
| System properties (8 checks) | **5 / 8** | **8 / 8** | CogniMesh |
| Schema drift handling | SQL Error (500) | Isolated (serves from Gold) | CogniMesh |
| Unsupported question | 404 Not Found | Composes query from metadata | CogniMesh |
| Freshness awareness | None | Built-in (is_stale flag) | CogniMesh |
| Dependency intelligence | None | Full graph + impact analysis | CogniMesh |
| Smart refresh | Cron (all tables) | Scheduled + real-time, only affected views | CogniMesh |
| Gold tables at 20 UCs | 17 tables | 4 views serving 20 UCs | CogniMesh |
| Gold refresh time | 1.19s | 0.92s (1.30x faster) | CogniMesh |
| Gold storage | Larger (17 tables) | 6.1 MB total (4 views) | CogniMesh |
| Cost to add new use case | 4 files, 78 lines | 1 JSON, 12 lines (15% of REST) | CogniMesh |
| Initial setup simplicity | 286 lines | 1,952 lines | REST |

### Honest caveat: the crossover requires packaging

The SLOC crossover at UC-22 assumes CogniMesh is installed as a dependency (`pip install cognimesh-core`), not copied into your repo. Without packaging, every team bears the full ~3,800 SLOC platform cost — and the crossover never arrives for small teams.

| Adoption model | Platform cost | Per-UC cost | Crossover vs REST |
|---|---|---|---|
| `pip install cognimesh-core` | 0 SLOC (dependency) | 12 SLOC (1 JSON) | UC-22 |
| Single team, one repo | ~3,800 SLOC (one-time) | 12 SLOC (1 JSON) | UC-22 within that team |
| Copy entire repo per team | ~3,800 SLOC per team | 12 SLOC (1 JSON) | Never favorable for small teams |

CogniMesh is pip-installable (`pip install -e .` from the repo). We recommend installing it as a dependency, not vendoring it.

### Latency Results (median, 100 iterations)

| Use Case | REST API | CogniMesh | Delta |
|----------|----------|-----------|-------|
| UC-01 Customer Health | 1.64ms | 2.85ms | +1.21ms |
| UC-02 Top Products | 1.47ms | 3.22ms | +1.75ms |
| UC-03 At-Risk Customers | 2.40ms | 5.75ms | +3.35ms |

REST wins on raw latency (~1-3ms faster per query). CogniMesh wins on everything else (8/8 system properties vs 5/8 for REST). The latency overhead buys lineage, audit, freshness awareness, drift detection, and tiered fallback — all included in every response.

### The 8-Property Scorecard

| # | Property | REST (dbt stack) | CogniMesh |
|---|----------|-------------------|-----------|
| 1 | Discovery | **Yes** (static endpoint list) | **Yes** (semantic UC matching) |
| 2 | Lineage | **Yes** (dbt manifest) | **Yes** (column-level, live) |
| 3 | Audit Trail | **Yes** (middleware logging) | **Yes** (per-query, per-UC) |
| 4 | Cost Attribution | **Yes** (audit cost_units) | **Yes** (tiered cost model) |
| 5 | Change Governance | No (dbt has no approval workflow) | **Yes** (approval queue) |
| 6 | Freshness Awareness | **Yes** (dbt run_results) | **Yes** (TTL-based, live) |
| 7 | Tiered Fallback | No (404 for unknown) | **Yes** (T2 Silver + T3 explain) |
| 8 | Schema Drift Detection | No (Gold SQL fails) | **Yes** (materialized isolation) |
| | **Score** | **5/8** | **8/8** |

### What Makes This a Fair Comparison

The REST baseline is not a strawman. It represents what a competent team builds with dbt:

- **Audit middleware** — FastAPI middleware logging every request with latency and cost
- **dbt manifest lineage** — Column-level lineage from `manifest.json`, served via API
- **dbt freshness** — Model freshness from `run_results.json`, served via API
- **Capability discovery** — Static endpoint listing via `/api/v1/discover`
- **API key auth** — Basic authentication via `X-API-Key` header

**Where CogniMesh still wins** (the 3 properties REST can't match):

| Property | Why REST Can't | CogniMesh Approach |
|---|---|---|
| **Change Governance** | dbt has no approval workflow — changes deploy directly | Approval queue: nothing changes in Gold without human sign-off |
| **Tiered Fallback** | Unknown query = 404. No intelligence. | T2 composes SQL from Silver with dbook metadata. T3 explains why it can't. |
| **Schema Drift Isolation** | Gold SQL references Silver columns directly — rename breaks everything | Gold views are materialized snapshots. Drift in Silver doesn't break serving. |

### Documents

| Document | What It Contains |
|----------|-----------------|
| **[Visual Benchmark Report](https://shurikm.github.io/CogniMesh/benchmark/results/report.html)** | Full benchmark report with charts, scorecards, measured results at 20 UCs. |
| **[Design Document](https://shurikm.github.io/CogniMesh/cognimesh.html)** | Architecture, design decisions, comparison, and implementation roadmap. |
| **[One-Pager](https://shurikm.github.io/CogniMesh/docs/onepager.html)** | Single-page overview of CogniMesh — architecture, key results, value proposition. |

---

## MCP Server

CogniMesh exposes all capabilities as MCP tools for direct agent integration:

```bash
# Run the MCP server
python -m cognimesh_core.mcp_server
```

Configure in Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "cognimesh": {
      "command": "python",
      "args": ["-m", "cognimesh_core.mcp_server"],
      "env": {"COGNIMESH_DATABASE_URL": "postgresql://..."}
    }
  }
}
```

| Tool | Description |
|------|-------------|
| `cognimesh_query` | Route questions through T0/T2/T3 with lineage and freshness |
| `cognimesh_discover` | List available data capabilities |
| `cognimesh_check_drift` | Detect Silver schema drift via dbook hashing |
| `cognimesh_refresh` | Trigger Gold view refresh |
| `cognimesh_impact_analysis` | What breaks if Silver changes? |
| `cognimesh_provenance` | Trace Gold columns to Silver sources |

---

## Installation

```bash
# From the repo
pip install -e ".[dbook]"

# Then create your app
from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.gateway import Gateway
# ... configure and run
```

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

# 4. Run all 90 benchmark tests
make bench

# 5. Generate the report
make report
```

### What `make bench` Runs

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

---

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

---

## How CogniMesh Works (in 30 seconds)

1. **Register a Use Case** — write a JSON file: "What is the health status of customer X?" + required fields + freshness TTL
2. **System derives Gold** — CogniMesh creates an optimized Gold table from Silver, registers column-level lineage, sets up freshness tracking, and builds the dependency graph
3. **Agent queries** — `POST /query {"question": "..."}` → Gateway matches UC → serves from Gold (T0) with lineage + freshness + audit
4. **Unsupported question?** — Gateway composes SQL from Silver metadata (T2) or explains why it can't (T3). No 404s.
5. **Schema changes?** — Gold layer isolates agents from Silver drift. System detects and flags changes.
6. **Dependency intelligence** — impact analysis shows which Gold views and UCs break if a Silver table changes. Provenance traces any Gold column back to its Silver source.
7. **Smart refresh** — Scheduled refresh is the primary mode: check TTLs, rebuild only stale views, report what changed. Real-time mode (Postgres LISTEN/NOTIFY) available for UCs that need immediate freshness. At 20 UCs, this means refreshing 3 views instead of 20.

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
POST /refresh/scheduled      — Run scheduled refresh cycle (primary mode)
POST /refresh/check          — Auto-refresh stale views (legacy)
GET  /refresh/plan           — Preview what would be refreshed

GET  /schema/drift            — Check Silver schema for structural changes (dbook)
```

---

## What's NOT in the Benchmark (Yet)

| Feature | Status | Why Skipped |
|---------|--------|-------------|
| MCP server | **Done** | 6 MCP tools wrapping the Gateway: query, discover, check_drift, refresh, impact_analysis, provenance. See [MCP Server](#mcp-server) section. |
| Access control & agent scoping | **Done** | Per-UC permissions, agent identity enforcement |
| Approval queue | **Done** | Nothing changes in Gold without human approval |
| LLM-based UC routing | Planned | Benchmark uses deterministic keyword matching for reproducibility |
| SQLMesh integration | **Done** | Managed Gold materialization with full DAG support |
| Multi-agent load testing | Planned | Single-agent sufficient to prove the architecture |
| Production data volumes | Planned | 200K orders sufficient for latency comparison |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Data models | Pydantic v2 |
| API framework | FastAPI |
| Database | Gold: Postgres / DuckDB / MongoDB / StarRocks / ClickHouse (serving DB — OLTP or OLAP) · Silver/Bronze: any (Iceberg, Delta, Spark, Snowflake) |
| DB driver | psycopg 3 + connection pool |
| Test framework | pytest + pytest-benchmark |
| Package manager | uv |
| LLM (production) | Pluggable: OpenAI / Anthropic / Ollama |
| Schema intelligence | [dbook](https://github.com/ShurikM/dbook) >=0.1.0 — database metadata compiler (optional, for rich schema introspection) |
| Agent interface | REST API (FastAPI) + MCP server (mcp Python SDK) |

## License

Apache 2.0
