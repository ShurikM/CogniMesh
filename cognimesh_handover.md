# CogniMesh — Session Handover

## What we built in this session

We designed **CogniMesh** — an open source Python library (Apache 2.0) that acts as an
intelligent data mesh layer between AI agents and structured data platforms.

The full design document is saved as `cognimesh.html`. This file is the handover context
to continue the design and implementation discussion.

---

## The problem CogniMesh solves

Today teams hand-build REST APIs or GraphQL schemas over a pre-defined Gold layer for agents
to consume. Both approaches work well at small scale but don't scale as the number of agents
and use cases grows — every new agent question requires a new engineering cycle.

CogniMesh replaces this with a declarative, self-improving serving layer:
- Teams register **Use Cases (UCs)** — questions agents need to answer
- CogniMesh derives optimal Gold views from those UCs via SQL Mesh
- Exposes them via **MCP** (Model Context Protocol) — no schema knowledge needed by agents
- Observes usage patterns and surfaces optimization suggestions to human operators
- Gold layer evolves from actual usage, not upfront design

**Not claiming:** observability and explainability as exclusive features — any solution can
add these. CogniMesh includes them built-in as convenience, not as differentiators.

**Real differentiators:**
1. Near-zero maintenance per new UC — declarative registration, SQL Mesh derives the rest
2. Self-improving Gold layer — derived from actual usage patterns
3. Tiered fallback — no hard failure for unsupported UCs (T0 → T1 → T2 → T3)
4. Scales with agent count without linear engineering cost

---

## Architecture summary

```
Consuming agents (any LLM / framework)
         │ MCP
┌────────▼──────────────────────────────────────┐
│  CogniMesh Gateway (MCP Server)               │
│  ┌──────────────┐ ┌───────────┐ ┌──────────┐  │
│  │ Capability   │ │ Embedded  │ │Material- │  │
│  │ Index        │ │ Agent     │ │ization   │  │
│  │ UC → view map│ │ routes Q  │ │ Engine   │  │
│  │ MCP tools    │ │ → UC →    │ │ suggests │  │
│  │ auto-updated │ │ Gold view │ │ new views│  │
│  └──────────────┘ └───────────┘ └──────────┘  │
│  ┌────────────────────────────────────────┐    │
│  │ Observability Engine                   │    │
│  │ OpenTelemetry → ClickHouse → Grafana   │    │
│  └────────────────────────────────────────┘    │
└───────────────────────┬───────────────────────┘
                        │
┌───────────────────────▼───────────────────────┐
│  SQL Mesh Layer                               │
│  Consolidation check → SQL generator →        │
│  Partition optimizer → Lineage tracker        │
│  All Gold changes require human approval      │
└───────────────────────┬───────────────────────┘
                        │
┌───────────────────────▼───────────────────────┐
│  Gold Layer — derived from UCs, not designed  │
│  Pre-joined · partitioned per access pattern  │
└───────────────────────┬───────────────────────┘
                        │
┌───────────────────────▼───────────────────────┐
│  Silver · Bronze                              │
│  Any medallion platform — Spark, DuckDB,      │
│  Delta, Iceberg, Postgres, Snowflake, BigQuery │
└───────────────────────────────────────────────┘
```

---

## Key design decisions (all resolved)

| Decision | Resolution |
|---|---|
| Tier 2 guardrails | Environment parameters — `COGNIMESH_T2_MAX_ROWS`, `_MAX_SECONDS`, `_MAX_COST_UNITS` |
| Auto-promotion threshold | Phase 1: reported metric only. Phase 2: configurable threshold |
| Agentic health monitor autonomy | Phase 1: human-in-loop — **important governance gate** |
| Multi-tenancy | Per-model scoping. Per-tenant optional, not required |
| SQL Mesh tooling | Pluggable adapter interface. Default: SQLMesh. Snowflake / Databricks adapters in Phase 2 |
| Embedded LLM | Pluggable via Protocol. Phase 2: A/B test routing via LLM-as-judge (DeepEval-style) |
| UC conflict resolution | Phase 1: surfaces structured suggestions with conflict detail — human decides. Phase 2: threshold-based auto-resolution rules |

---

## Use Case (UC) structure

The authoring unit is a **question**, not a table.

```json
{
  "id": "UC-01",
  "question": "Natural language description of what this UC answers",
  "consuming_agent": "agent_id",
  "required_fields": ["field_a", "field_b"],
  "access_pattern": "individual_lookup | bulk_query | aggregation",
  "freshness_ttl": "1h",
  "freshness_rationale": "why this TTL",
  "phase": "1",
  "gold_view": "assigned by SQL Mesh after human approval"
}
```

---

## Fallback tiers

| Tier | Condition | Cost | Action |
|---|---|---|---|
| T0 | UC in index, Gold view active | ~10ms, zero joins | Serve directly |
| T1 | Fields exist across 2–3 Gold views | ~50ms, no Silver | Compose in memory, log pattern |
| T2 | Not in Gold at all | Seconds, guardrailed | Generate SQL on Silver, log as UC candidate |
| T3 | Would exceed guardrail | 0ms | Reject with explanation + ETA |

---

## Product phases

**Phase 1 — current target (fully human-in-loop)**
- Human authors UCs as structured records
- SQL Mesh derives Gold views, human approves every change
- UC conflicts surfaced as structured suggestions, human decides
- T2 hit frequency reported — human promotes manually
- LLM-as-judge evaluation wired in (activated Phase 2)
- Full observability and lineage built in

**Phase 2 — usage-driven automation**
- T2 patterns auto-promoted to UC candidates
- Threshold-based auto-approval for low-risk changes
- Auto-resolution of common UC conflict patterns
- TTL auto-adjustment from data change frequency
- A/B testing of routing LLMs
- Snowflake Dynamic Tables + Databricks Materialized Views adapters

**Phase 3 — fully agentic**
- Self-managing Gold lifecycle
- Humans retained at cost and policy gates only

**Governing principle:** No phase skips the one before it. Phase 1 builds the human feedback
loop that Phase 2 automates.

---

## Comparison vs alternatives

| Dimension | Dedicated REST API | GraphQL | CogniMesh |
|---|---|---|---|
| Performance | Excellent | Good | Excellent at T0 |
| Maintenance per new UC | High — new endpoint each time | Low–medium | Near zero |
| Scales with agent count | Poorly | Reasonably | Well |
| Unsupported UCs | Hard failure | Partial composition | Tiered fallback |
| Observability | Addable | Addable | Built in |
| Explainability | Addable | Addable | Built in |
| Gold lifecycle | Manual | Partial | Automated |

---

## Proposed repo structure

```
cognimesh/
├── cognimesh/
│   ├── core/           # models, UC registry, capability index
│   ├── gateway/        # MCP server, embedded agent, fallback tiers
│   ├── mesh/           # consolidation, SQL gen, partition, lineage, adapters
│   ├── observability/  # OTel, ClickHouse/DuckDB store, signals
│   ├── approval/       # human approval queue, CLI, suggestions
│   └── config.py
├── tests/
│   ├── unit/
│   ├── integration/    # DuckDB as data platform, no external deps
│   └── eval/           # DeepEval routing quality tests
└── examples/
```

---

## Tech stack

- **Models:** Pydantic v2
- **MCP:** `mcp[server]` (official MCP Python SDK)
- **LLM:** OpenAI + Anthropic + Ollama (pluggable via Protocol)
- **SQL Mesh:** `sqlmesh` Python API (default adapter)
- **Observability:** OpenTelemetry SDK → ClickHouse (prod) / DuckDB (dev)
- **Approval DB:** SQLite (stdlib, no extra dep)
- **CLI:** `typer` + `rich`
- **Eval:** `deepeval`
- **Packaging:** `uv` + `pyproject.toml`

---

## Phase 1 invariants — never break

1. Nothing changes in Gold without human approval
2. Agents never see Silver schema — embedded agent resolves internally
3. T2 is always guardrailed — check all three limits before executing
4. Capability index is the agent-facing surface — UC registry is internal state
5. Lineage is pre-computed at materialization time, not generated at query time
6. All numeric limits come from CogniMeshConfig — never hardcode

---

## Day-One Comparison: REST API vs CogniMesh (same data)

We designed a concrete comparison starting from identical Bronze/Silver data (DuckDB e-commerce dataset)
with 3 UCs (Customer Health, Top Products, At-Risk Customers). Both approaches serve the same questions —
the difference is everything around the answer.

### Measurement dimensions (8 total)
1. Developer lifecycle — time-to-first-UC, marginal UC cost, lines of code, maintenance
2. Runtime performance — T0/T1/T2 latency, throughput, resource overhead
3. Agent experience — discovery, error quality, schema evolution handling, response metadata
4. Governance — lineage, audit trail, change approval workflow
5. Resilience — unsupported query fallback, schema drift tolerance, freshness visibility
6. Observability — time-to-first-dashboard, cost attribution granularity
7. Evolvability — marginal UC cost, Gold consolidation, dead view cleanup
8. Total cost of ownership — setup cost, per-UC cost, operational cost, compute cost

### Honest assessment at UC = 1

**REST wins (3 things):**
- Raw T0 latency: ~2-5ms faster (no MCP overhead, no embedded agent routing)
- Setup simplicity: fewer moving parts for a single static UC
- Compute footprint: thinner runtime, no embedded agent

**CogniMesh wins (11 things):**
- Discovery, unsupported query handling, error quality, schema drift tolerance,
  lineage, observability, audit trail, freshness management, change governance,
  cost attribution, response metadata

### Developer hours crossover

| UC Count | REST cumulative | CogniMesh cumulative | Delta |
|---|---|---|---|
| 0 (setup) | 0h | 3h | REST ahead by 3h |
| 1 | 8h | 3.5h | CogniMesh ahead by 4.5h |
| 3 | 24h | 4.5h | CogniMesh ahead by 19.5h |
| 10 | 80h | 7h | CogniMesh ahead by 73h |

Crossover happens at UC = 1. CogniMesh's one-time setup (3h) is less than building
one REST endpoint with Gold table + tests + docs (8h).

### System completeness gap

To bring REST to parity with CogniMesh's day-one capabilities (discovery, lineage,
freshness, audit, fallback, cost attribution, schema drift isolation, change governance)
requires 7-12 additional developer-days. Most teams never build these.

### Key insight

REST gives you a fast pipe. CogniMesh gives you a governed, observable, self-documenting
data serving layer. The 2-5ms latency premium is the price of the platform. The platform
is what makes UC = 2 through UC = 100 possible without linear engineering cost.

The full visual comparison is in `cognimesh.html` Section 01c.

---

## Gold Layer Consolidation & Crossover Analysis

We designed a 10-UC scenario showing how CogniMesh's Gold layer consolidates as UCs grow:
- REST creates 10 independent Gold tables (1 per UC) with 45 overlapping columns
- CogniMesh consolidates to 5 Gold views (50% fewer) by detecting Silver source overlap
- Consolidation ratio at UC=50: 0.24 (12 views for 50 UCs)

### Crossover points — when CogniMesh wins each dimension

| Dimension | Crossover |
|-----------|-----------|
| Marginal dev hours | UC = 1 (always) |
| Governance (8 properties) | UC = 1 (always) |
| Unsupported query handling | UC = 1 (always) |
| Gold table count | UC = 5 |
| Refresh time + storage | UC = 5 |
| Total SLOC | UC = 22 |
| Query latency (projected) | UC = 22-25 |
| ALL dimensions | UC = 25 |

### Self-improving behavior

T2-to-UC promotion cycle: unsupported question → T2 serves immediately → audit log
detects pattern → UC candidate generated → human approves → promoted to T0 (85× faster).
REST equivalent: 404 → support ticket → developer builds endpoint → 2-5 business days.

The full analysis with charts is in `benchmark/results/report.html` sections 12-14.

---

## Suggested first steps in Claude Code

1. Scaffold repo structure
2. Implement `cognimesh/core/models.py` — all Pydantic models
3. Implement `cognimesh/config.py` — CogniMeshConfig with env var loading
4. Implement `cognimesh/core/uc_registry.py` — UseCase CRUD with JSON persistence
5. Unit tests for all three — `uv run pytest tests/unit/` must pass before moving on
6. Then: capability index → gateway → mesh → observability → CLI

Build bottom-up. Do not start on MCP server or embedded agent until models are solid.
