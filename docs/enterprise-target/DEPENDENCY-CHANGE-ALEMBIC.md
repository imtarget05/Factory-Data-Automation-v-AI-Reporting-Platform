# WAVE 2 — Alembic for database schema migrations

```text
DEPENDENCY CHANGE REQUEST

package        : alembic
version        : ==1.20.0
reason         : production database schema migration framework
submitted_by   : worker factory/core
applied_by     : Integrator (requirements.txt is integrator-owned)
```

## Version justification

Verified against the PyPI JSON API, not guessed:

| Constraint | This repo | Alembic 1.20.0 | Compatible |
|---|---|---|---|
| Python | 3.12.13 (`.venv`) | `>=3.10` | yes |
| SQLAlchemy | 2.1.1 | `SQLAlchemy>=2.0` | yes |
| py3.12 classifier | — | present | yes |

Pinned exactly (`==1.20.0`) rather than ranged. A migration framework's
behaviour — ordering, transaction boundaries, downgrade semantics — is part of
your schema's history, and a floating range means the meaning of an applied
revision can change under you. `requirements.txt` otherwise uses `>=` ranges for
libraries, but this one earns an exception: a `requirements.txt` with a mix of
ranges and pins looks untidy until the first time a migration produces a
different result on two machines.

## Why Alembic and not a home-grown runner

WAVE 2 needs durable schema evolution for `ETLRunManifest`, `QuarantineRecord`,
`StageExecution`, `QualityGateResult`, `ReportManifest`, the durable idempotency
constraint, and later replay/audit metadata.

A custom runner looks light on day one and then becomes production infrastructure
that must itself supply: version ordering, migration history, transactional DDL,
failure recovery, downgrade semantics, drift detection, and a CI contract.
Those are exactly the problems Alembic already solves and has been solving since
2011. Writing them again would mean writing them *worse*, and the cost would not
show up until the first failed migration in production.

Alembic's transactional-DDL support also matters specifically here: on PostgreSQL
a migration runs inside a transaction, so a failure leaves the database at the
previous revision rather than half-migrated.

## Runtime and dev consumers

| Consumer | Use |
|---|---|
| Runtime | explicit `alembic upgrade head` step in the deployment/migration job — **never** implicit `Base.metadata.create_all()` |
| Development | migration integration tests: empty DB → head; previous revision → head; repeat head; induced failure |
| Application startup | read-only schema-revision compatibility check (report expected revision, refuse to run against an unknown one) |

`create_all` survives only in isolated unit-test helpers, clearly separated from
the migration path.

## Tests proving the requirement

1. fresh PostgreSQL → `alembic upgrade head` → expected tables, indexes and constraints present
2. database at previous revision with representative rows → `upgrade head` → data preserved, new objects present, constraints correct
3. at head → `upgrade head` again → idempotent, no duplication, no destructive change
4. intentionally broken migration in an isolated fixture → failure surfaces, database is **not** recorded at head, mutation never committed

These are written on Core-owned paths (`tests/test_migrations_*.py`) and run
against a real PostgreSQL container.

## Live-schema caveat

Local migration evidence and live Azure evidence are **separate**. As of
2026-10-02 the live Azure subscription contains **no PostgreSQL server** for
Factory (read-only inventory: only `ca-factory-api` + a shared managed
environment + a shared Log Analytics workspace). So there is no deployed schema
to import, and no live history to invent. The first migration is a deliberate
baseline, not a reconstruction of history that does not exist.