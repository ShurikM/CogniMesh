# CogniMesh Roadmap

## Current State (v0.1.0)

Architecture validated with:
- dbook schema intelligence (FKs, enums, PII, drift detection)
- MCP server (6 tools)
- Honest benchmark: dbt REST stack (5/8) vs CogniMesh (8/8)
- T2 production guards (EXPLAIN cost, table size, concurrency)
- 90 tests, GitHub Actions CI
- Approval queue governance

## Inspiration

This roadmap is informed by:
- [Meta's Analytics Agent](https://medium.com/@AnalyticsAtMeta/inside-metas-home-grown-ai-analytics-agent-4ea6779acfb3) -- 70K users, millions of tables, usage-based intelligence
- [MLOps Community: Memory Layer for AI Agents](https://mlops.community/engineering-the-memory-layer-for-an-ai-agent-to-navigate-large-scale-event-data/) -- navigating large-scale event data with schema-as-memory, multi-level vector search, and pre-compiled reasoning paths

## Phase 2: Usage-Based Intelligence

**Inspired by:** Meta's Shared Memory ("88% of queries rely on tables from last 90 days")

### 2.1 Audit Log Mining
- Analyze `cognimesh_internal.audit_log` to extract query patterns
- Build per-agent table affinity scores (which agent queries which tables most)
- Identify successful T2 compositions as Gold UC promotion candidates
- Generate usage-based table descriptions that supplement dbook's structural metadata
- **Why:** CogniMesh already collects this data but doesn't learn from it

### 2.2 Auto-Promote T2 to Gold
- When a T2 pattern is queried >N times with consistent results, suggest it as a UC
- Generate the UC JSON automatically from the T2 audit trail
- Submit to approval queue for human review
- **Why:** Meta's insight -- encode knowledge once, share across conversations

### 2.3 Agent Domain Scoping
- Maintain per-agent table affinity index from audit logs
- Pre-filter Silver tables before T2 scoring (only consider tables the agent has used)
- Weight T2 table scoring by agent affinity (not just keyword matching)
- At scale (1000+ Silver tables), this is required -- T2 cannot score every table
- **Why:** Meta's 88% hypothesis -- agents work in bounded domains

## Phase 3: Semantic Validation Layer

**Inspired by:** Meta's Custom Validations ("WAU should be < 8 billion")

### 3.1 Natural-Language Validation Rules
- Extend UC model with `validation_rules: list[str]`:
  ```json
  {
    "id": "UC-01",
    "validation_rules": [
      "customer_count should be less than 500,000",
      "always filter by is_active=true",
      "revenue values should be positive"
    ]
  }
  ```
- Check rules via LLM before returning T0/T2 results
- Separate validation AI layer (like Meta's approach -- a second LLM call that validates the first)
- Fail open: if validation LLM is unavailable, log warning but return results
- **Why:** CogniMesh validates cost/safety but not business meaning

### 3.2 Result Sanity Checking
- Post-execution validation: compare results against expected ranges defined in validation rules
- Flag anomalies (e.g., revenue doubled overnight -- likely a data issue, not real growth)
- Add `warnings` field to QueryResult metadata (list of strings, human-readable)
- Distinguish between hard failures (block result) and soft warnings (return with caveat)
- **Why:** Meta's "the agent can self-correct" -- we should catch obvious errors

### 3.3 Semantic Aliases in UC Definitions
- Allow UC authors to add domain-specific term mappings:
  ```json
  {
    "id": "UC-01",
    "semantic_aliases": {
      "churn risk": ["customer_profiles.risk_score", "orders.days_since_last_order"],
      "revenue": ["orders.total_amount", "order_items.subtotal"]
    }
  }
  ```
- Feed aliases into CapabilityIndex to improve matching for paraphrased questions
- Implements Meta's Ingredients concept within CogniMesh's existing UC model
- **Why:** "How healthy is this customer?" and "What is the health status of customer X?" should match the same UC

## Phase 4: Memory Layer

**Inspired by:** MLOps Community article -- "The schema acts as the agent's long-term memory structure"

The MLOps article demonstrates that an AI agent's ability to answer questions correctly depends on the quality of the metadata layer between the agent and the data. They call this the "memory layer" -- a structured, pre-compiled representation of what the data IS, what it MEANS, and how it CONNECTS. The key architectural insight: do the hard reasoning at build time (schema design, relationship encoding, embedding generation), not at query time.

### 4.1 Schema Memory (dbook evolution)

**Core insight from article:** "The schema represents the most consequential decision in the entire pipeline. In the context of Agentic RAG, the schema acts as the agent's long-term memory structure."

- **Pre-compiled reasoning paths:** The article encodes entity relationships as graph edges so the agent traverses pre-built paths rather than reasoning about joins at runtime. Apply to dbook: pre-compile FK chains into traversal paths that T2 can use directly. Instead of T2 discovering that `orders.customer_id -> customers.id` at composition time, dbook should pre-compile "customer -> orders -> order_items" as a named traversal path with JOIN clauses ready to use.
- **Multi-granularity metadata:** The article maintains three levels of metadata (chunk-level detail, entity-level overview, speaker-level expertise). Apply to dbook: generate metadata at three levels:
  1. **Column-level:** current ColumnInfo (types, enums, PII, sample values)
  2. **Table-level:** table summaries, purpose descriptions, common query patterns (new)
  3. **Domain-level:** cross-table concept maps, business entity definitions (new)
- **Type strictness as memory:** The article emphasizes that storing `yt_views` as Integer (not String) directly determines what queries the agent can generate. dbook already captures types but should surface type-aware query hints: "this column is Integer, supports >, <, BETWEEN" vs "this column is VARCHAR, supports LIKE, =".
- **Idempotent schema compilation:** The article uses UUID5-based deterministic IDs so re-running the pipeline never creates duplicates. Apply to dbook: extend SHA256 drift detection to produce deterministic compilation artifacts. If the schema hasn't changed, the compiled BookMeta should be byte-identical, enabling cache-friendly refresh and CI-based diffing of schema changes.
- **Schema extensibility without tool changes:** The article's schema allows adding new years of conference data without modifying agent tools. Validate that CogniMesh maintains this property: adding a new Silver table or UC should never require changes to Gateway, CapabilityIndex, or MCP tools.
- **Why:** The article proves that schema-first design is the dominant strategy for agent data access. dbook is already schema-first; these enhancements make it a true long-term memory structure.

### 4.2 Query Memory

**Core insight from article:** Constrained semantic search -- filter by metadata FIRST, then search only within the matching subset -- "dramatically improves relevance."

- Cache successful query plans (tier, UC match, composed SQL, table set) keyed by normalized question embedding
- When a similar question comes in, retrieve the cached plan as a starting point
- TTL-based invalidation tied to Gold freshness (when Gold view refreshes, invalidate cached plans that used it)
- Store cache in `cognimesh_internal.query_cache` table:
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
- Implement the article's constrained search pattern for T2: use cached table affinity to narrow the Silver search space before running CapabilityIndex scoring
- **Why:** Reduce T2 composition latency for repeated patterns; the article shows this is the single biggest performance optimization

### 4.3 Context Accumulation

**Core insight from article:** The article uses graph connections (TalkHasSpeaker, TalkHasTranscriptChunk) to maintain relationships across queries. A question about a speaker automatically inherits context about their talks.

- Build conversation-level context for multi-turn agent interactions via MCP session state
- Agent asks Q1, gets answer, then asks follow-up Q2 -- Q2 should inherit context from Q1:
  - Which UCs were matched in Q1
  - Which tables and columns were used
  - What filter values were applied
  - What the result shape looked like
- Store context in MCP server session (in-memory, expires with session)
- Use accumulated context to bias UC matching and T2 composition for follow-up questions
- Example: Q1 = "Show me customer 42's orders" (matches UC-02, uses orders table). Q2 = "What about their returns?" -- context from Q1 tells us the agent is looking at customer 42, so T2 should look for returns tables with customer_id joins
- **Why:** Single-shot queries miss the iterative investigation pattern. Meta's agent excels at chained queries; CogniMesh should support this without requiring full agent autonomy

### 4.4 Embedding-Based Discovery (optional)

**Core insight from article:** Three separate embedding indexes (transcript chunks, talk-level meta, speaker bios) enable intent-specific semantic search. "By modeling the domain as a graph, we effectively pre-compile the reasoning paths... This significantly reduces the risk of hallucinations and retrieval errors."

- Add optional sentence embeddings to CapabilityIndex for semantic UC matching
- Generate embeddings for: UC descriptions, Gold view column descriptions, dbook table summaries
- Use cosine similarity as a secondary signal alongside keyword/IDF scoring
- Separate embedding spaces per intent (like the article's three descriptor sets):
  1. **UC-level embeddings** -- match questions to use cases
  2. **Table-level embeddings** -- match questions to Silver tables for T2
  3. **Column-level embeddings** -- match specific terms to columns for T2 composition
- Keep keyword/IDF as primary (zero-dependency, deterministic); embeddings as optional boost
- **Why:** The article demonstrates that vector search catches paraphrased questions that keyword matching misses. "How healthy is this customer?" would miss keyword match on "health_score" but would match semantically.

## Phase 5: Self-Correction for T2

**Inspired by:** Meta's iterative reasoning loop ("write code, execute it, see real results, and decide what to do next")

### 5.1 Limited Retry Loop
- If T2 returns 0 rows: retry with relaxed filters or different table selection
- If T2 returns unexpected results (negative values for SUM, count exceeding table row count): retry with modified aggregation
- Max 2 retries to maintain determinism and prevent runaway loops
- Each retry uses a different strategy:
  - Retry 1: same tables, relaxed WHERE clause (remove most restrictive filter)
  - Retry 2: different table selection (next-best CapabilityIndex match)
- Log all attempts in audit trail (original + retries, with reason for each retry)
- Return the best result across attempts (prefer non-empty, valid results)
- **Why:** Current T2 is one-shot -- empty results go straight to T3. Meta shows that one retry often finds the answer.

### 5.2 Reasoning Trace
- Add `reasoning_steps: list[str]` to QueryResult metadata
- Document the full decision chain:
  - Which UCs were considered and their confidence scores
  - Why this tier was chosen (T0 match vs T2 fallback vs T3 rejection)
  - What validations passed/failed (EXPLAIN cost, table size, business rules)
  - For T2: which Silver tables were scored, why the winner was selected, how columns were mapped
  - For retries: what went wrong, what changed, what improved
- Format as human-readable strings, not structured objects (agents and humans both read these)
- **Why:** Meta's "Thinking UI" shows planning and reasoning steps in real time. Agents and humans need to understand the decision chain for trust and debugging.

## Phase 6: Scale Validation

### 6.1 Production-Scale Benchmark
- 50M+ rows in Silver, 1000+ columns across 50+ tables
- Network-attached Postgres (separate machine, not localhost)
- 100-500 concurrent agent connections via MCP
- Sustained load over hours (not just burst tests)
- Memory profiling under concurrent T2 composition (dbook BookMeta in memory * N connections)
- Measure: T0 p50/p95/p99 latency, T2 composition time, dbook introspection time at scale
- **Why:** Current benchmark is toy scale (10K rows, localhost). The SLOC argument only holds if CogniMesh performs at production scale.

### 6.2 Offline Introspection for Large Schemas
- For schemas with 1000+ tables, dbook introspection should be a scheduled offline job
- Compile BookMeta to disk (JSON or MessagePack), load from cache at startup
- Incremental recompile: only re-introspect tables whose SHA256 hash changed
- Separate "compile" step from "serve" step (like the MLOps article separates ingestion from querying)
- **Why:** Synchronous introspection of 1000+ tables at startup is not viable in production

### 6.3 Multi-Engine Support
- Test with DuckDB, StarRocks, ClickHouse as Gold serving layer
- Test with Spark+Iceberg as Silver layer
- Validate dbook introspection across SQL dialects (SQLAlchemy Inspector abstracts most, but edge cases exist)
- Test T2 SQL composition against non-Postgres SQL dialects (SQLGlot handles this, but needs validation)
- **Why:** Production deployments won't all be single-Postgres

## Phase 7: Community and Ecosystem

**Inspired by:** Meta's 4,500+ community recipes driving 77% weekly active rate

### 7.1 UC Marketplace
- Publish, discover, and fork UC definitions across teams
- Versioned UC packages (like Meta's Cookbooks) with dependency tracking
- UC templates for common patterns: "customer 360", "product analytics", "funnel analysis"
- Import/export as JSON bundles with dbook schema requirements documented
- **Why:** Meta's community adoption drove 77% weekly active rate. CogniMesh UCs are already JSON -- make them shareable.

### 7.2 dbook MCP Server
- Standalone MCP server for dbook (schema intelligence without governance)
- Agents can use dbook directly for exploratory analysis (understand schema, discover tables, check relationships)
- CogniMesh MCP for governed serving, dbook MCP for understanding
- Tools: `describe_table`, `find_tables_for_concept`, `explain_relationship`, `check_drift`
- **Why:** Different agents have different needs. Exploratory agents want schema understanding; production agents want governed data.

### 7.3 PyPI Release
- Publish `cognimesh-core` to PyPI (gateway, UC registry, audit, approval)
- Publish `dbook` to PyPI (schema introspection, concept index, drift detection)
- Versioned releases with changelog and migration guides
- `pip install cognimesh-core dbook` should get a working system in under 5 minutes
- **Why:** The SLOC crossover argument (12-line UC vs 200-line dbt model) only holds with `pip install`

### 7.4 Dependency Graph as Queryable Tool
- Expose the Silver -> Gold -> UC dependency graph as an MCP tool
- Agents can ask: "What data sources feed into the customer health score?"
- Answer directly from the lineage graph without hitting Gold or Silver
- Inspired by the MLOps article's graph traversal as a first-class query primitive
- **Why:** Currently the dependency graph is only used for impact analysis, not for agent queries

## Priority Matrix

| Phase | Impact | Effort | Priority |
|-------|--------|--------|----------|
| 2.1 Audit log mining | High | Medium | P1 |
| 2.2 Auto-promote T2 to Gold | High | Medium | P1 |
| 7.3 PyPI release | Medium | Low | P1 |
| 3.1 NL validation rules | High | Medium | P2 |
| 5.2 Reasoning trace | Medium | Low | P2 |
| 4.2 Query memory/caching | Medium | Medium | P2 |
| 2.3 Agent domain scoping | High | Medium | P2 |
| 3.3 Semantic aliases | Medium | Low | P2 |
| 4.1 Schema memory (dbook evolution) | High | High | P2 |
| 5.1 T2 retry loop | Medium | Low | P3 |
| 4.3 Context accumulation | Medium | High | P3 |
| 6.1 Scale benchmark | High | High | P3 |
| 6.2 Offline introspection | Medium | Medium | P3 |
| 7.2 dbook MCP server | Medium | Low | P3 |
| 7.4 Dependency graph tool | Low | Low | P3 |
| 4.4 Embedding-based discovery | Medium | High | P4 |
| 3.2 Result sanity checking | Medium | Medium | P4 |
| 7.1 UC marketplace | Medium | High | P4 |
| 6.3 Multi-engine support | Medium | High | P4 |
