# dbook Integration

> Back to [README](../README.md)

CogniMesh integrates with [dbook](https://github.com/ShurikM/dbook) — a database metadata compiler that extracts schema intelligence for AI agent consumption. This replaces the shallow `information_schema.columns` introspection with rich structural metadata.

## What dbook Provides

| Capability | Before (vanilla) | After (with dbook) |
|---|---|---|
| **T2 Column Matching** | Fuzzy keyword match on column names | Concept-boosted scoring with IDF weighting |
| **T2 Row Estimation** | Heuristic defaults (1-50 rows) | Actual `row_count` from dbook introspection |
| **Enum Validation** | None — raw string matching | dbook detects enum-like columns, validates/corrects filter values |
| **SQL Validation** | Execute and catch errors | Pre-flight validation via SQLGlot (table/column/FK/enum checks) |
| **Schema Drift** | Detected reactively when Gold refresh fails | Proactive SHA256 hash comparison on every scheduled refresh |
| **PII Awareness** | None — no sensitivity detection | dbook scans column names + sample data via Presidio, marks sensitivity levels |
| **UC Discovery** | Keyword overlap scoring | Semantic concept index boosts matches for domain terms |

## How It Works

1. **Startup**: `DbookBridge` creates a read-only SQLAlchemy connection and runs `introspect_all(schemas=["silver"])` — capturing columns, FKs, enums, row counts, and sample data.
2. **Concept Index**: `generate_concepts(book)` builds a term→table/column mapping (e.g., "customer" → customer_profiles, orders.customer_id).
3. **Injection**: Rich metadata is injected into `TemplateComposer` and `CapabilityIndex` at startup.
4. **T2 Path**: Composed SQL is validated against the dbook schema before execution. Invalid queries are rejected to T3 with actionable suggestions. PII-marked columns (email, phone, SSN, credit card) are respected — T2 avoids selecting sensitive columns in ad-hoc results.
5. **Refresh Cycle**: `scheduled_refresh()` calls `check_drift()` — re-introspects Silver and compares SHA256 hashes. Drift events are logged with affected Gold views.

## Configuration

| Env Var | Default | Description |
|---|---|---|
| `COGNIMESH_DBOOK_ENABLED` | `true` | Enable/disable dbook integration |
| `COGNIMESH_DBOOK_SAMPLE_ROWS` | `5` | Sample rows per table during introspection |
| `COGNIMESH_DBOOK_INCLUDE_ROW_COUNT` | `true` | Include row counts (requires COUNT(*) query) |
| `COGNIMESH_T2_MAX_EXPLAIN_COST` | `50000` | Max Postgres EXPLAIN cost before T2 query is rejected |
| `COGNIMESH_T2_MAX_SOURCE_ROWS` | `10000000` | Max source table rows (from dbook) before T2 query is rejected |
| `COGNIMESH_T2_MAX_CONCURRENT` | `3` | Max concurrent T2 queries (semaphore) |

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/schema/drift` | GET | Check Silver schema for structural changes |

dbook is an **optional dependency** — CogniMesh runs without it, falling back to basic `information_schema` metadata.

All 19 dbook integration tests pass in the benchmark: schema-aware T2 composition uses rich metadata (FKs, enums, sample data), drift detection works proactively via SHA256 hash comparison on every scheduled refresh, semantic discovery via the concept index boosts UC matching for domain terms, and T2 production guards (EXPLAIN cost check, table size guard, concurrency semaphore) are verified.

## T2 Production Safety Guards

T2 Silver fallback composes SQL dynamically — which is powerful but dangerous without proper guards. CogniMesh implements three production-grade safety mechanisms:

| Guard | What it does | Config | Default |
|-------|-------------|--------|---------|
| **EXPLAIN cost check** | Runs `EXPLAIN (FORMAT JSON)` before execution. Rejects if Postgres cost estimate exceeds threshold. | `COGNIMESH_T2_MAX_EXPLAIN_COST` | 50,000 |
| **Table size guard** | Uses dbook's actual row counts to reject queries against Silver tables larger than threshold. | `COGNIMESH_T2_MAX_SOURCE_ROWS` | 10,000,000 |
| **Concurrency semaphore** | Limits concurrent T2 queries to prevent connection pool saturation. | `COGNIMESH_T2_MAX_CONCURRENT` | 3 |

These complement the existing guards (statement timeout, result row limit) to prevent catastrophically expensive queries on large Silver tables.

### T2 Rejection Flow

If any guard triggers, the query is rejected to T3 with the specific reason (`explain_cost_exceeded`, `source_table_too_large`, `t2_concurrency_limit`) and actionable metadata (actual cost, row count, limits). The agent knows exactly why the query was rejected and what the limits are.

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

### The Combined Pitch

> CogniMesh + dbook: Build Gold views for your top 20 critical queries (T0). Let dbook-powered T2 handle the other 80% of ad-hoc questions directly from Silver — correctly, with enum values, validated SQL, and PII awareness. No more "we don't have a Gold table for that."

### Claim Refinement

| Claim | Accurate? |
|---|---|
| "No Gold needed for agent DISCOVERY" | Yes — dbook |
| "No Gold needed for agent UNDERSTANDING" | Yes — dbook |
| "No Gold needed for PERFORMANCE" | No — T0 Gold is still fastest |
| "No Gold needed for GOVERNANCE" | No — audit, access control, freshness need infrastructure |
| "FEWER Gold views needed" | Yes — T2 + dbook handles what used to require pre-built Gold |

dbook and CogniMesh are complementary, not contradictory. dbook shrinks the Gold layer from "everything must be pre-built" to "only performance-critical queries need Gold."
