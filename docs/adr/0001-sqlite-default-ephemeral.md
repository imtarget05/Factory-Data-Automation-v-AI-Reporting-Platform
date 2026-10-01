# ADR-0001: SQLite-Default Ephemeral Store vs Managed Postgres on Free Tier

- **Status:** Superseded by [ADR-0002](0002-migrate-to-postgresql-blob-storage.md)
- **Date:** 2026-09-27 (Superseded 2026-10-01)

## Context

The pipeline is batch (ETL → Parquet/SQLite → dashboard renders) running on
free-tier hosts (Render/serverless) with no concurrent writers and no
multi-user row access. A managed Postgres would add provisioning, secrets,
connection management, and cost for a workload that reads files and writes
artefacts.

## Decision

Default to SQLite (+ timestamped Parquet artefacts in `data/processed/`) as
the store; treat Postgres as a future, not a default. Keep the persistence
boundary narrow (`save_processed`, loader cache) so migration is a swap, not a
rewrite.

## Consequences

- Positive: zero-provision deploy, zero credentials, artefacts double as audit
  trail; free-tier friendly.
- Negative: single-writer ceiling; concurrent dashboard writers or multi-plant
  ingestion will outgrow it — migration trigger explicitly defined.

## Alternatives

- Managed Postgres from day one: correct at scale, but idle cost + ops for a
  batch job that never needs concurrent writes; premature infrastructure.
- CSV-only, no DB: simplest, but loses queryability for the dashboard cache and
  audit joins the KPI layer relies on.
