# ADR-0002: Migration to PostgreSQL & Azure Blob Storage for Enterprise Distributed Ingestion

- **Status:** Accepted
- **Date:** 2026-10-01
- **Supersedes:** [ADR-0001](0001-sqlite-default-ephemeral.md)

## Context

ADR-0001 established SQLite + timestamped local Parquet files as the default store for batch processing, explicitly identifying its limits:
> *"single-writer ceiling; concurrent dashboard writers or multi-plant ingestion will outgrow it — migration trigger explicitly defined."*

The Enterprise Target platform elevates the Factory Data Platform to an enterprise distributed topology:
1. **Multi-Replica Ingestion & API**: Running across multiple Azure Container App replicas with concurrent telemetry ingestion and reporting.
2. **Tiered Lakehouse Storage**: Replacing ephemeral local folders with Azure Blob Storage tiered containers (`raw-landing`, `silver-clean`, `gold-marts`, `quarantine-corrupt`) governed by TLS 1.2 and soft-delete policies.
3. **Decoupled Telemetry Ingestion**: High-throughput telemetry ingestion via Azure Service Bus Standard (`factory-telemetry-inbox` queue) with deduplication (10-minute window) and DLQ routing.
4. **Centralized Run Manifest & Audit Ledger**: Recording deterministic ETL runs, schema validation hashes, quarantine metrics, and data lineage in an ACID-compliant, concurrently accessible database.

Therefore, the migration trigger documented in ADR-0001 has been formally activated.

## Decision

1. **Enterprise Object Storage**:
   - Adopt **Azure Blob Storage** for the multi-tier data lakehouse:
     - `raw-landing`: immutable append-only ingestion.
     - `silver-clean`: validated, cleaned, standardized records.
     - `gold-marts`: dimensionally modeled business aggregation marts for KPI calculations.
     - `quarantine-corrupt`: isolated payloads failing deterministic contract gates.
2. **Durable Truth & Metadata Store**:
   - Adopt **Azure Database for PostgreSQL Flexible Server** (v16) for ETL run manifests, schema change history, and data quality audit trails.
3. **Asynchronous Messaging**:
   - Utilize **Azure Service Bus** (`factory-telemetry-inbox`) for decoupled, ordered, deduplicated machine sensor telemetry.
4. **Preserve Fast Offline Seam**:
   - Retain local SQLite and filesystem Parquet fallback when cloud environment variables (`DATABASE_URL`, `AZURE_STORAGE_CONNECTION_STRING`) are unset.
   - Ensures the 290+ offline test suite continues to execute in under 35 seconds with zero external network or container dependencies.

## Consequences

- **Positive**:
  - Eliminates single-writer file lock contention across multiple API/ETL replicas.
  - Multi-tier cloud storage isolation prevents corrupted telemetry from contaminating reporting marts.
  - Provable, tamper-evident audit history of all pipeline runs and data contract rejections.
  - Complete continuity for developer velocity and CI stability via the offline storage adapter.
- **Negative**:
  - Adds schema migration steps (`alembic` / SQL scripts) for cloud environments.
