# CURRENT STATE — Factory-Data-Automation-v-AI-Reporting-Platform

```text
measured_at : 2026-10-01
method      : read-only (git + filesystem). Azure NOT probed. Test suites NOT run.
mutations   : `git fetch --all --prune` only (remote-tracking refs; working tree untouched)
rule        : no number appears below unless it was measured here, or is explicitly
              labelled CARRIED_FORWARD_NOT_REMEASURED.
```

## 1. Identity

| Field | Value |
|---|---|
| remote | `https://github.com/imtarget05/Factory-Data-Automation-v-AI-Reporting-Platform.git` |
| **canonical ref (`origin/main`)** | `563a7d40db6b95dacfeefc8dc36995ff59d39a81` |
| local `HEAD` | `16d8129461ddc75f80fbeb1e9cbc2d829bcebe34` (branch `main`) |
| drift vs origin | **+3 ahead / 0 behind** — 3 `docs(...)` commits |
| worktree | **CLEAN** |

Canonical SHA is `563a7d4`; `16d8129` is unpushed local docs drift.

## 2. Infrastructure as deployed today

| Field | Value |
|---|---|
| IaC language | **Bicep** (Terraform: **NOT PRESENT** — 0 `*.tf` files) |
| entrypoints | `infra/main.bicep` |
| modules | `infra/modules/{apps,database,keyvault,messaging,network,observability,storage}` |
| parameters | `infra/parameters/{dev,prod}.bicepparam` |
| invariant checker | `infra/check_invariants.py` |
| validation | `infra/validate.sh`, `infra/bicepconfig.json` |
| CI | `.github/workflows/iac-validate.yml` *(also: `ci.yml`, `ci-live.yml`, `build-container.yml`, `keepalive.yml`, `llm-gateway.yml`)* |

`storage` and `messaging` modules are present → Blob zone + Service Bus seams exist in Bicep.

## 3. Verified seams present in source

> Presence in source ≠ verified at runtime. This section records existence only.

- Service Bus telemetry consumer — `app/etl/servicebus_consumer.py::TelemetryConsumer`
- Consumer test — `tests/test_servicebus_consumer.py`
- PostgreSQL run metadata models referenced by the consumer test — `app/database/models.py` (`ETLRunManifest`, `QuarantineRecord`)

## 4. Open defects / documented gaps (carried, with source)

- **[factory-clean-clone]** — the canonical suite needs a **generated fixture**; a clean clone cannot reproduce it. `290 passed / 5 skipped / 4 xfailed` at deployed SHA `be4ace3`; the 4 xfailed are **mutation controls that must never pass**. *source: `docs/PORTFOLIO-FLAGSHIP-MATRIX.md`*
- **[factory-ai-report-guard]** — the quality gate is live AND attested, but the **BAD/UNKNOWN branch was never triggered in the cloud**, and `REAL_MODEL` is unverified (no LLM reachable from the container). *source: same.*

## 5. NOT YET MEASURED (fail-closed)

- test suite @ `origin/main` ............ **UNMEASURED**
- CI status @ `origin/main` ............. **UNMEASURED**
- Azure live revision / image digest .... **UNMEASURED**
- idempotency (duplicate Blob event / duplicate Service Bus message) .... **UNMEASURED**
- cost exposure ......................... **UNMEASURED**

CARRIED_FORWARD_NOT_REMEASURED (audit docs only — do NOT quote as verified): live revision `ca-factory-api--0000002` running `be4ace3` by digest `sha256:7c3e81b7…` with a SLSA attestation; cloud auth guard rejects unauthenticated requests (401) — **the authenticated success path is NOT VERIFIED** (the probe carried no credential).

## 6. Hazards

- `$HOME` (`/Users/mainguyenbinhtan`) is a **DIRTY worktree** of `FlashSale-Backend`. `Projects/.git` is an **empty stub** → any git run from `Projects/` resolves to `$HOME`. **All git MUST use `git -C <abs repo path>`.**
- Local `main` is 3 commits ahead of `origin/main` → never treat local `HEAD` as canonical.
