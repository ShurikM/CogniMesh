# Architecture

> Back to [README](../README.md)

## Deployment Modes

<p align="center">
  <img src="architecture.svg" alt="CogniMesh Architecture" width="700">
</p>

CogniMesh is an intelligent serving layer for AI agents with two deployment modes:

### Mode 1: Connect (start here)

Connect to your existing Silver layer. CogniMesh introspects the schema, builds Gold views from UC definitions, and serves agents with lineage, observability, and access control. Your existing dbt/Spark/Airflow pipeline stays untouched.

### Mode 2: Manage (full platform)

CogniMesh + SQLMesh manages the entire Bronze→Silver→Gold pipeline. Full lineage from raw source to agent response. Complete schema knowledge across all layers. Intelligent refresh based on the full DAG.

## Migration Path

Start with Mode 1 — zero disruption. Migrate Silver tables into SQLMesh models one at a time. Each migrated table gains full Bronze→Silver→Gold lineage. Eventually, CogniMesh has complete observation of all layers needed to support current and future UCs.

## Why Gold Must Be a Serving Database

Agents do individual lookups — "health of customer X", "orders for product Y." That needs sub-10ms latency. Open table formats (Iceberg/Delta) on object storage take 100-1000ms per lookup.

CogniMesh separates **transformation storage** from **serving storage**:

- **Bronze/Silver**: can live on a lakehouse (Iceberg, Delta, Spark) — cheap, batch-optimized
- **Gold**: must be a serving database — OLTP (Postgres, DuckDB, MongoDB) or OLAP (StarRocks, ClickHouse, Druid) — fast, agent-optimized

SQLMesh manages transformations across all layers. CogniMesh materializes Gold into the serving DB and serves agents from there.

## Engine Configurations

### Single-engine

All layers on one database (Postgres, StarRocks, DuckDB). SQLMesh manages Bronze→Silver→Gold in the same engine. Simple setup, ideal for small/medium teams or getting started.

### Multi-engine

Silver on a lakehouse (Spark + Iceberg/Delta), Gold on a serving database (Postgres, StarRocks, ClickHouse). SQLMesh manages transformations on each engine natively. CogniMesh orchestrates cross-engine materialization — reads Silver from the lakehouse, materializes Gold into the serving DB. This is the enterprise configuration for teams with existing lakehouse infrastructure.

Both configurations get the same CogniMesh capabilities: UC registry, lineage, observability, smart refresh, dependency intelligence, security.

## The Five Pillars

Across both modes, CogniMesh provides five core capabilities:

### Explainability

Every response traces back to source data. Full lineage in Mode 2, Gold→Silver lineage in Mode 1.

### Observability

Every query logged: who asked, what it cost, how fresh the data is.

### Self-service

Register a UC with a 12-line JSON. System derives Gold, consolidates overlapping views. Scheduled refresh is the primary mode: check TTLs, rebuild only stale views, report what changed. Real-time mode (Postgres LISTEN/NOTIFY) available for UCs that need immediate freshness.

### Flexibility

Unknown questions composed from metadata (T2), not 404s. T2 patterns auto-promoted to Gold UCs.

### Security

Agent identity and scoping, per-UC access control, row-level data isolation.
