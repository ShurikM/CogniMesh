# Benchmark: dbt REST Stack vs CogniMesh

> Back to [README](../README.md)

We built **two complete implementations** serving the same 20 business questions from the same local Postgres database (10K customers, 500 products, 200K orders — toy scale). Then we measured architectural properties. See [scale limitations](#scale-reality-check) for what this does and does not prove.

## Key Results

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

## Honest Caveat: The Crossover Requires Packaging

The SLOC crossover at UC-22 assumes CogniMesh is installed as a dependency (`pip install cognimesh-core`), not copied into your repo. Without packaging, every team bears the full ~3,800 SLOC platform cost — and the crossover never arrives for small teams.

| Adoption model | Platform cost | Per-UC cost | Crossover vs REST |
|---|---|---|---|
| `pip install cognimesh-core` | 0 SLOC (dependency) | 12 SLOC (1 JSON) | UC-22 |
| Single team, one repo | ~3,800 SLOC (one-time) | 12 SLOC (1 JSON) | UC-22 within that team |
| Copy entire repo per team | ~3,800 SLOC per team | 12 SLOC (1 JSON) | Never favorable for small teams |

CogniMesh is pip-installable (`pip install -e .` from the repo). We recommend installing it as a dependency, not vendoring it.

## Latency Results

Median latency across 100 iterations (all tests run on localhost):

| Use Case | REST API | CogniMesh | Delta |
|----------|----------|-----------|-------|
| UC-01 Customer Health | 1.64ms | 2.85ms | +1.21ms |
| UC-02 Top Products | 1.47ms | 3.22ms | +1.75ms |
| UC-03 At-Risk Customers | 2.40ms | 5.75ms | +3.35ms |

REST wins on raw latency (~1-3ms faster per query). CogniMesh wins on architectural properties (8/8 system properties vs 5/8 for REST). The latency overhead buys lineage, audit, freshness awareness, drift detection, and tiered fallback — all included in every response. Note: all latency numbers are from localhost with 10K rows; production latency at scale will differ significantly.

## The 8-Property Scorecard

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

## What Makes This a Fair Comparison

The REST baseline is not a strawman. It represents what a competent team builds with dbt:

- **Audit middleware** — FastAPI middleware logging every request with latency and cost
- **dbt manifest lineage** — Column-level lineage from `manifest.json`, served via API
- **dbt freshness** — Model freshness from `run_results.json`, served via API
- **Capability discovery** — Static endpoint listing via `/api/v1/discover`
- **API key auth** — Basic authentication via `X-API-Key` header

### Where CogniMesh Still Wins

CogniMesh wins on the 3 properties REST can't match:

| Property | Why REST Can't | CogniMesh Approach |
|---|---|---|
| **Change Governance** | dbt has no approval workflow — changes deploy directly | Approval queue: nothing changes in Gold without human sign-off |
| **Tiered Fallback** | Unknown query = 404. No intelligence. | T2 composes SQL from Silver with dbook metadata. T3 explains why it can't. |
| **Schema Drift Isolation** | Gold SQL references Silver columns directly — rename breaks everything | Gold views are materialized snapshots. Drift in Silver doesn't break serving. |

## Reference Documents

| Document | What It Contains |
|----------|-----------------|
| **[Visual Benchmark Report](https://shurikm.github.io/CogniMesh/benchmark/results/report.html)** | Full benchmark report with charts, scorecards, measured results at 20 UCs. |
| **[Design Document](https://shurikm.github.io/CogniMesh/cognimesh.html)** | Architecture, design decisions, comparison, and implementation roadmap. |
| **[One-Pager](https://shurikm.github.io/CogniMesh/docs/onepager.html)** | Single-page overview of CogniMesh — architecture, key results, value proposition. |

## What This Benchmark Proves (and What It Doesn't)

**This benchmark proves architectural properties, not production performance.**

| What it proves | What it does NOT prove |
|---|---|
| CogniMesh has lineage, audit, freshness, governance | That these work at 50M rows or 500 concurrent agents |
| T2 fallback composes correct SQL from Silver | That T2 composition is fast on large Silver tables |
| Schema drift is detected and isolated | That drift detection scales to 1000-table schemas |
| dbt REST stack gets 5/8 properties with effort | That either approach handles network-attached Postgres latency |
| Adding a UC is 12 SLOC vs 78 SLOC | That operational cost follows the same ratio |

## Scale Reality Check

- **Dataset:** 10K customers, 200K orders, local Postgres. This is a toy. Sub-10ms latency at this scale is trivially achievable with `SELECT * FROM table WHERE id = $1`.
- **Concurrency:** Throughput tests run 1/5/10/25 concurrent requests. Production agents may run 500+.
- **Network:** All tests run against localhost. Production Postgres adds 1-5ms network RTT.
- **Lineage overhead:** Attaching lineage metadata to every response is cheap at 10K rows. At 50M rows with column-level tracking across 1000 tables, the lineage lookup itself becomes a performance concern.

### What Would a Production-Scale Benchmark Look Like?

- 50M+ rows in Silver, 1000+ columns across 50+ tables
- Network-attached Postgres (or Postgres on a separate machine/cloud)
- 100-500 concurrent agent connections
- Sustained load over hours (not seconds)
- Memory profiling under concurrent T2 composition
- Lineage lookup latency at scale

We haven't built this yet. The current benchmark is a **proof of architecture**, not a **proof of scale**. If you're evaluating CogniMesh for production, run the benchmark against your own data at your own scale — the `make all` command works with any Postgres instance.

## What's NOT in the Benchmark (Yet)

| Feature | Status | Why Skipped |
|---------|--------|-------------|
| MCP server | **Done** | 6 MCP tools wrapping the Gateway: query, discover, check_drift, refresh, impact_analysis, provenance. See [MCP Server](#mcp-server) section. |
| Access control & agent scoping | **Done** | Per-UC permissions, agent identity enforcement |
| Approval queue | **Done** | Nothing changes in Gold without human approval |
| LLM-based UC routing | Planned | Benchmark uses deterministic keyword matching for reproducibility |
| SQLMesh integration | **Done** | Managed Gold materialization with full DAG support |
| Multi-agent load testing | Planned | Single-agent sufficient to prove the architecture |
| Production data volumes | Planned | 200K orders sufficient for architectural comparison, not scale validation |

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
