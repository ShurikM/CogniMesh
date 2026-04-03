# CogniMesh Roadmap

> Governed data serving platform for autonomous AI agents.
> dbook handles understanding. CogniMesh handles safe, audited, governed access.

## References

These documents informed this roadmap:

| Document | Key Insight | Location |
|----------|-------------|----------|
| Meta Analytics Agent | Usage-based intelligence, NL validation, iterative reasoning | [Medium article](https://medium.com/@AnalyticsAtMeta/inside-metas-home-grown-ai-analytics-agent-4ea6779acfb3) |
| MLOps Memory Layer | Schema-as-memory, constrained search, query caching, multi-turn context | [MLOps Community article](https://mlops.community/engineering-the-memory-layer-for-an-ai-agent-to-navigate-large-scale-event-data/) |
| Meta deep analysis | Full comparison: Meta vs CogniMesh architecture | `docs/research/meta_analytics_agent_analysis.md` |
| MLOps deep analysis | Full comparison: memory layer vs CogniMesh/dbook | `docs/research/mlops_memory_layer_analysis.md` |

## Current State (v0.1.0)

- dbook schema intelligence integrated (FKs, enums, PII, drift detection)
- MCP server with 6 tools
- Honest benchmark: dbt REST stack (5/8) vs CogniMesh (8/8)
- T2 production guards (EXPLAIN cost, table size, concurrency)
- 90 tests, GitHub Actions CI
- Approval queue governance with full API

---

## Phase 2: Usage-Based Intelligence (P1)

**Inspired by:** Meta's Shared Memory -- "88% of queries rely on tables from last 90 days"

Meta's most powerful idea is building agent context from actual behavior. CogniMesh already logs every query in `cognimesh_internal.audit_log` but does not mine it for intelligence. This phase transforms raw audit data into actionable signals that improve routing, composition, and Gold coverage.

### 2.1 Audit Log Mining

Mine `cognimesh_internal.audit_log` to extract patterns from historical query traffic:

- **Table affinity per agent:** Which agent queries which tables most frequently. Build a weighted affinity index: `{agent_id: {table: hit_count, last_used, avg_confidence}}`. This becomes the agent's "personal domain" (Meta's term).
- **T2 success patterns:** Identify T2 compositions that consistently return valid results (non-zero rows, no warnings, confidence > 0.6). These are candidates for Gold promotion.
- **Temporal patterns:** Track query frequency by hour/day/week. Identify peak access patterns for capacity planning and cache warming.
- **Column co-occurrence:** Which columns are frequently requested together. Informs T2 composition -- if agents always ask for `customer_name` alongside `order_total`, the T2 composer should include both when it sees either.
- **Implementation:** Scheduled offline job (daily cron or triggered after N new audit entries). Results stored in `cognimesh_internal.agent_affinity` and `cognimesh_internal.t2_patterns` tables.
- **Why:** CogniMesh already collects this data but throws away the intelligence. Meta's entire Shared Memory system is built on this principle: learn from what agents actually do, not just what schemas declare.

### 2.2 Auto-Promote T2 to Gold

When a T2 pattern is queried repeatedly with consistent results, automatically generate a UC definition and submit it for human approval:

- **Trigger:** T2 pattern queried >N times (configurable, default 10) within 30 days, with >80% returning non-empty results.
- **Generation:** Extract from audit trail: the composed SQL, the tables used, the columns selected, the typical filter patterns. Generate a complete UC JSON with `question`, `sql_template`, `columns`, `lineage`.
- **Submission:** Insert into `cognimesh_internal.approval_queue` with `source: "auto-promoted"`, `evidence: {hit_count, success_rate, sample_queries}`. Human reviewer sees the evidence alongside the UC definition.
- **Feedback loop:** If rejected, record the rejection reason and suppress re-promotion of the same pattern for 90 days.
- **Why:** Meta encodes knowledge once and shares it across conversations. Auto-promotion is the mechanism: T2 discovers the pattern, usage validates it, approval queue governs it, Gold materializes it for performance.

### 2.3 Agent Domain Scoping

Maintain a per-agent table affinity index that pre-filters Silver tables before T2 scoring:

- **Build:** From audit log mining (2.1), maintain `cognimesh_internal.agent_affinity` with columns: `agent_id`, `schema_name`, `table_name`, `query_count`, `last_queried_at`, `avg_confidence`.
- **Apply:** When an agent submits a T2 query, CapabilityIndex first filters Silver tables to only those the agent has queried before (or tables in the same schemas). If the filtered set produces a match above threshold, use it. If not, fall back to full Silver scan.
- **Weight:** T2 table scoring incorporates affinity as a signal: `final_score = keyword_score * 0.7 + affinity_score * 0.3`. Agents that frequently query `orders` get better T2 results for order-related questions.
- **Cold start:** New agents (no history) get full Silver scan. After 10 queries, affinity begins to influence scoring.
- **Scale implications:** At 1000+ Silver tables, full scoring is O(N) per query. Agent domain scoping reduces N to the agent's working set (typically 10-30 tables, per Meta's 88% hypothesis). This is required for production scale.
- **Why:** Meta's central insight -- agents work in bounded domains. Scoping to the domain before scoring eliminates noise and improves accuracy.

---

## Phase 3: Semantic Validation (P2)

**Inspired by:** Meta's Custom Validations -- "WAU should be < 8 billion", "Always filter by is_test=false"

CogniMesh validates cost and safety (EXPLAIN cost, table size, concurrency) but not business meaning. Meta validates meaning via natural-language rules checked by a separate AI. This phase adds semantic guardrails on top of operational ones.

### 3.1 Natural-Language Validation Rules

Extend the UC model with an optional `validation_rules` field:

```json
{
  "id": "UC-01",
  "question": "How many active customers do we have?",
  "validation_rules": [
    "customer_count should be less than 500,000",
    "always filter by is_active=true unless explicitly asked for inactive",
    "revenue values should be positive",
    "date range should not exceed 2 years"
  ]
}
```

- **Pre-return check:** After T0/T1 query execution but before returning results, send the validation rules + query results to an LLM. The LLM returns `{pass: true}` or `{pass: false, violation: "customer_count is 2.3M, expected < 500K"}`.
- **Separate validation call:** Use a fast, cheap model (Gemini Flash, Claude Haiku) specifically for validation. This is Meta's approach -- a separate AI layer that checks the primary AI's output.
- **Fail-open policy:** If the validation LLM is unavailable (rate limit, timeout), log a warning but return results. Validation is advisory, not blocking, unless the UC explicitly sets `validation_mode: "strict"`.
- **Result metadata:** Add `validation` field to QueryResult: `{rules_checked: 4, passed: 3, warnings: ["customer_count is 2.3M, expected < 500K"]}`.
- **Why:** CogniMesh's operational guards prevent expensive/dangerous queries. Semantic validation prevents wrong answers. Together they cover both axes of query safety.

### 3.2 Result Sanity Checking

Post-execution validation that catches anomalies without requiring explicit rules:

- **Zero-row detection:** If a T0 Gold query that typically returns data suddenly returns 0 rows, flag it. Compare against historical row counts from audit log.
- **Order-of-magnitude shifts:** If a metric that was ~100K last week is now 10M, add a warning: "value is 100x higher than 7-day average".
- **Negative aggregates:** SUM/AVG returning negative values for columns that should be non-negative (detected from column metadata or historical patterns).
- **NULL spike detection:** If >50% of a result column is NULL when historically it was <5%, flag potential data quality issue.
- **Output:** Add `warnings: list[str]` field to QueryResult metadata. Warnings are human-readable strings. Distinguish `severity: "info" | "warning" | "error"`. Only `error` blocks result delivery (in strict mode).
- **Why:** Meta's agent self-corrects by observing unexpected results. CogniMesh should catch obvious anomalies before the consuming agent has to.

---

## Phase 4: Query Intelligence (P2)

**Inspired by:** MLOps memory layer -- constrained search, caching, multi-turn context

The MLOps article demonstrates that constraining the search space before executing expensive operations dramatically improves relevance. This phase brings that principle to CogniMesh's query routing and adds caching and multi-turn support.

### 4.1 Query Plan Caching

Cache successful query plans so repeated or similar questions skip the full routing pipeline:

- **Cache table:** `cognimesh_internal.query_cache`:
  ```sql
  CREATE TABLE cognimesh_internal.query_cache (
    question_hash TEXT PRIMARY KEY,
    question_text TEXT,
    tier TEXT,            -- T0/T1/T2
    uc_id TEXT,
    composed_sql TEXT,
    tables_used TEXT[],
    hit_count INTEGER DEFAULT 1,
    last_hit_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    ttl_seconds INTEGER
  );
  ```
- **Cache key:** Normalize the question (lowercase, strip whitespace, remove stop words), then SHA256 hash. This handles minor phrasing variations.
- **TTL:** Tied to Gold freshness. When a Gold view refreshes, invalidate cached plans that reference it. Default TTL: 1 hour for T2 plans, 24 hours for T0 plans.
- **Warm-up:** On startup, pre-warm cache from audit log (most frequent questions from last 7 days).
- **Cache miss cost:** Full routing pipeline runs (~50ms for T0, ~200ms for T2). Cache hit cost: single hash lookup + SQL execution (~5ms overhead).
- **Why:** The MLOps article shows constrained search as the single biggest performance optimization. Caching is the ultimate constraint -- skip the search entirely for known patterns.

### 4.2 Constrained UC Matching

Apply the MLOps constrained search pattern to UC discovery:

- **Step 1:** Determine agent domain from affinity index (Phase 2.3). If agent has history, restrict UC matching to UCs that reference tables in the agent's domain.
- **Step 2:** Within the constrained UC set, run CapabilityIndex scoring (keyword + concept matching).
- **Step 3:** If constrained matching produces no result above threshold, expand to full UC set.
- **Benefit:** For an agent whose domain covers 5 UCs out of 200, matching is 40x faster and produces fewer false positives.
- **Integration with T2:** For T2 fallback, constrained matching filters Silver tables by agent affinity before scoring. The T2 composer works with a smaller, more relevant table set.
- **Why:** The MLOps article demonstrates that "filter first, then search" dramatically improves relevance. This is the same principle applied to UC and table discovery.

### 4.3 Multi-Turn Context

Build conversation-level context for multi-turn agent interactions via MCP session state:

- **Session state:** MCP server maintains per-session context: `{last_uc_matched, last_tables_used, last_filters_applied, last_result_shape, turn_count}`.
- **Context inheritance:** Q2 in a session inherits context from Q1:
  - If Q1 matched UC-02 (orders), Q2 "what about their returns?" biases toward UCs and tables related to the same entity (customer) with the same filter (customer_id = 42).
  - If Q1 selected columns A, B, C, Q2 "add the total" augments the column set rather than starting fresh.
- **Pronoun resolution:** When Q2 contains "their", "that", "those", resolve against Q1's result context. "Show me customer 42's orders" followed by "what's their lifetime value?" -- "their" resolves to customer_id = 42.
- **Session expiry:** In-memory, expires after 30 minutes of inactivity. No persistence -- multi-turn context is ephemeral.
- **Scope:** MCP sessions only. REST API queries are stateless by default (can opt-in via `session_id` header).
- **Why:** Meta's agent excels at chained queries -- "why did signups drop?" leads to follow-up investigations. Single-shot queries miss this iterative pattern. Multi-turn context enables CogniMesh to support investigation workflows without full agent autonomy.

---

## Phase 5: Self-Correction (P3)

**Inspired by:** Meta's iterative reasoning loop -- "write code, execute it, see real results, and decide what to do next"

CogniMesh's T2 is currently one-shot: compose SQL, validate, execute, return. If the result is empty or unexpected, the agent gets a T3 rejection rather than a chance to retry. Meta shows that one retry often finds the answer.

### 5.1 T2 Retry Loop

Add a limited self-correction loop for T2 compositions that return unexpected results:

- **Trigger conditions:** T2 returns 0 rows, or result contains only NULL values, or EXPLAIN cost of composed SQL exceeds guard but a simpler reformulation might work.
- **Retry strategy 1 (relaxed filters):** Remove the most restrictive WHERE clause filter and re-execute. If the original query was `WHERE status = 'active' AND created_at > '2024-01-01'`, retry with just `WHERE status = 'active'`.
- **Retry strategy 2 (different table):** If retry 1 still returns 0 rows, try the next-best table match from CapabilityIndex. If the first attempt used `customer_profiles`, retry 2 might use `customer_accounts`.
- **Max retries:** 2 (hard cap). Each retry is logged as a separate audit entry with `retry_number` and `retry_reason`.
- **Result selection:** Return the best result across attempts. Prefer: non-empty > empty, higher confidence > lower, fewer retries > more.
- **Cost accounting:** Each retry consumes cost units. Total cost = sum of all attempts. Agent sees the total cost, not per-attempt.
- **Why:** Current T2 is one-shot -- empty results go straight to T3 rejection. One retry recovers a significant fraction of these false rejections. Meta's iterative loop is unbounded; CogniMesh's is capped at 2 for determinism.

### 5.2 Reasoning Trace

Add a `reasoning_steps` field to QueryResult that explains the full decision chain:

- **Content:** List of human-readable strings documenting each decision:
  ```
  [
    "Received question: 'How many active customers do we have?'",
    "CapabilityIndex matched UC-01 (customer_health_score) with confidence 0.82",
    "Tier: T0 (Gold match above 0.6 threshold)",
    "Gold view: gold.customer_360, last refreshed 2h ago, TTL 24h",
    "Validation: 3/3 rules passed",
    "Result: 1 row, 5 columns, 0.045s execution time"
  ]
  ```
- **T2-specific entries:** Which Silver tables were scored, top 3 candidates with scores, why the winner was selected, how columns were mapped, what SQL was composed.
- **Retry entries:** What went wrong, what changed, what improved.
- **Format:** List of strings, not structured objects. Both agents and humans read these for debugging and trust.
- **Performance:** Reasoning trace is assembled during routing (no extra work). Adding it to the response adds ~200-500 tokens.
- **Why:** Meta's "Thinking UI" shows planning and reasoning steps in real time. Agents and operators need to understand why CogniMesh chose this tier, this UC, this SQL. Transparency builds trust and enables debugging.

---

## Phase 6: Scale Validation (P3)

### 6.1 Production-Scale Benchmark

Validate CogniMesh at realistic production scale:

- **Data scale:** 50M+ rows in Silver across 50+ tables with 1000+ columns. Realistic data distributions (skewed, sparse columns, large text fields).
- **Infrastructure:** Network-attached Postgres on a separate machine (not localhost). Measure real network latency in all benchmarks.
- **Concurrency:** 100-500 concurrent agent connections via MCP. Sustained load over hours, not just burst tests.
- **Memory profiling:** dbook BookMeta in memory multiplied by N concurrent connections. Identify memory ceiling and optimize (shared BookMeta across connections, lazy loading of table details).
- **Latency targets:** T0 p50 < 50ms, T0 p95 < 200ms, T2 p50 < 500ms, T2 p95 < 2s.
- **Throughput targets:** 100 queries/second sustained for T0, 20 queries/second for T2.
- **Why:** Current benchmark is toy scale (10K rows, localhost). The SLOC crossover argument (12-line UC vs 200-line dbt model) only holds if CogniMesh performs at production scale. This benchmark proves or disproves the architecture.

### 6.2 Multi-Engine Support

Validate CogniMesh against non-Postgres engines as Gold and Silver layers:

- **Gold layer engines:** DuckDB (embedded analytics), StarRocks (real-time OLAP), ClickHouse (columnar analytics). Each engine has different SQL dialect, materialization semantics, and performance characteristics.
- **Silver layer engines:** Spark+Iceberg (lakehouse), Snowflake (cloud warehouse), BigQuery (serverless).
- **dbook validation:** Confirm dbook introspection works across all dialects via SQLAlchemy Inspector. Document edge cases per dialect (e.g., BigQuery lacks FKs, Snowflake has case-sensitivity quirks).
- **T2 composition validation:** SQLGlot handles dialect translation, but T2 composition needs testing against each dialect's type system, function names, and JOIN semantics.
- **Why:** Production deployments span multiple engines. CogniMesh must work wherever the data lives.

---

## Phase 7: Ecosystem (P1-P4)

### 7.1 PyPI Release (P1)

Publish CogniMesh to PyPI for frictionless adoption:

- **Package:** `cognimesh-core` on PyPI. Includes gateway, UC registry, audit, approval queue, T0/T1/T2/T3 routing, MCP server.
- **Extras:** `cognimesh-core[postgres]`, `cognimesh-core[mcp]`, `cognimesh-core[dbook]`.
- **Getting started:** `pip install cognimesh-core[postgres,dbook]` + 12-line UC JSON + `cognimesh serve` -- working governed data server in under 5 minutes.
- **Versioned releases:** Semantic versioning, changelog, migration guides between versions.
- **Why:** The SLOC crossover argument only holds with `pip install`. Without it, setup friction negates the simplicity advantage.

### 7.2 UC Marketplace (P4)

Enable teams to publish, discover, and fork UC definitions:

- **Registry:** Centralized or git-backed registry of UC definition packages (like Meta's 4,500+ community-created Recipes).
- **Templates:** Pre-built UC packages for common patterns: "customer 360", "product analytics", "funnel analysis", "revenue reporting". Each template includes UC definitions, expected Silver schema, and example queries.
- **Versioning:** UC packages are versioned. Importing a UC package pins the version. Schema requirements are documented so teams know what Silver tables are needed.
- **Fork and customize:** Import a template, customize for your schema, publish back as a variant.
- **Why:** Meta's community adoption (4,500+ recipes, 77% weekly active) shows that knowledge sharing drives adoption. CogniMesh UCs are already JSON -- make them shareable and discoverable.

### 7.3 Dependency Graph as MCP Tool (P3)

Expose the Silver -> Gold -> UC dependency graph as a queryable MCP tool:

- **Tool:** `cognimesh_lineage` -- agents can ask "What data sources feed into the customer health score?" and get the full dependency chain without executing any query.
- **Use cases:** Impact analysis ("if I change the orders table, what UCs are affected?"), data discovery ("what Gold views use customer data?"), debugging ("why is this UC stale?").
- **Format:** Returns a structured lineage tree: Silver tables -> Gold views -> UCs, with column-level mappings at each hop.
- **Inspired by:** MLOps article's graph traversal as a first-class query primitive. Currently the dependency graph is only used internally for impact analysis -- exposing it to agents adds a new dimension of transparency.

---

## Priority Matrix

| Item | Impact | Effort | Priority |
|------|--------|--------|----------|
| 2.1 Audit log mining | High | Medium | P1 |
| 2.2 Auto-promote T2 to Gold | High | Medium | P1 |
| 7.1 PyPI release | Medium | Low | P1 |
| 3.1 NL validation rules | High | Medium | P2 |
| 5.2 Reasoning trace | Medium | Low | P2 |
| 4.1 Query plan caching | Medium | Medium | P2 |
| 2.3 Agent domain scoping | High | Medium | P2 |
| 4.2 Constrained UC matching | Medium | Low | P2 |
| 4.3 Multi-turn context | Medium | High | P3 |
| 5.1 T2 retry loop | Medium | Low | P3 |
| 6.1 Scale benchmark | High | High | P3 |
| 7.3 Dependency graph tool | Low | Low | P3 |
| 3.2 Result sanity checking | Medium | Medium | P3 |
| 6.2 Multi-engine support | Medium | High | P4 |
| 7.2 UC marketplace | Medium | High | P4 |
