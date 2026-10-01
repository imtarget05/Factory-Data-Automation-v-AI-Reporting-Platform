# CURRENT STATE — Factory-Data-Automation-v-AI-Reporting-Platform

```text
measured_at : 2026-10-02
method      : read-only (git + filesystem) + measured suite via
              .venv Python 3.12 (`pytest -m "not live and not infra"`),
              ruff check/format, fixture verify, `gh run list`.
              Azure NOT probed. Test suite NOT re-run beyond the single
              canonical measurement below.
mutations   : `git fetch --all --prune` only (remote-tracking refs; working tree untouched)
rule        : no number appears below unless it was measured here, or is explicitly
              labelled CARRIED_FORWARD_NOT_REMEASURED.
```

## 1. Identity

| Field | Value |
|---|---|
| remote | `https://github.com/imtarget05/Factory-Data-Automation-v-AI-Reporting-Platform.git` |
| **canonical ref (`origin/main`)** | `a0cd8892cb6745751deb89ea8b72a4a5dffb98dd` |
| local `HEAD` | `a0cd8892cb6745751deb89ea8b72a4a5dffb98dd` (branch `main`) |
| drift vs origin | **0 ahead / 0 behind** — in sync |
| worktree | **CLEAN** |
| stale writer retired | `ent/enterprise-target @ 03d1f20` retired 2026-10-02 after semantic supersession check (worktree removed, local branch deleted; no remote branch existed). See §7. |

Canonical SHA is `a0cd889`; the 2026-10-01 ledger (`563a7d4` +3 docs drift) is superseded.

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

## 5. MEASURED 2026-10-02 @ `a0cd889` (fail-closed for the rest)

- test suite: **303 collected → 294 passed / 5 skipped / 4 xfailed in 9.63 s**
  via `.venv` Python 3.12, `pytest tests/ -m "not live and not infra" --strict-markers`.
  System Python 3.14 is **NON-CANONICAL**: collection fails (4 errors,
  `ModuleNotFoundError: reportlab`) — missing declared environment
  dependency, NOT a repository regression.
- ruff: `ruff check app/ tests/` → **All checks passed**;
  `ruff format --check app/ tests/` → **71 files already formatted**.
- fixture: `python -m scripts.verify_fixture --blessed docs/expected/factory-fixture.json`
  → **PASS (schema=factory-fixture-v1, seed=42, 26119 rows)**.
- CI @ `origin/main`: **SUCCESS on `a0cd889`**
  (`CI/CD Pipeline` + `Build and Publish API Image to GHCR`,
  2026-10-01T17:14:21Z via `gh run list`). Previous `e78c6fa` CI run was **failure**.
- Azure live revision / image digest .... **UNMEASURED** (not probed; no mutation attempted)
- idempotency (duplicate Blob event / duplicate Service Bus message) .... **UNMEASURED**
- cost exposure ......................... **UNMEASURED**

CARRIED_FORWARD_NOT_REMEASURED (audit docs only — do NOT quote as verified): live revision `ca-factory-api--0000002` running `be4ace3` by digest `sha256:7c3e81b7…` with a SLSA attestation; cloud auth guard rejects unauthenticated requests (401) — **the authenticated success path is NOT VERIFIED** (the probe carried no credential).

## 6. Hazards

- `$HOME` (`/Users/mainguyenbinhtan`) is a **DIRTY worktree** of `FlashSale-Backend`. `Projects/.git` is an **empty stub** → any git run from `Projects/` resolves to `$HOME`. **All git MUST use `git -C <abs repo path>`.**
- Terraform is **NOT_STARTED** (0 `*.tf` files). Factory is **THIRD** in migration
  order (1 MAIA → 2 Helpdesk → 3 Factory). No Terraform edits until Phase 0 closes.

## 7. Stale writer retirement — `ent/enterprise-target @ 03d1f20` (2026-10-02)

Merge-base with canonical `a0cd889` is `e5caa2a`. Direction
`a0cd889...03d1f20`: 30 files changed, +6266 (additive-only —
every entry `A`, no `M`/`D`, so it cannot regress `main` by
modification; risk is only obsolescence/duplication).

| # | Capability in `03d1f20` | `main @ a0cd889` equivalent | Classification |
|---|---|---|---|
| 1 | Subscription-scope `infra/main.bicep` (536 lines: platform/data/apps/network, identity-first, RBAC-last) | Resource-group `infra/main.bicep` (114 lines, `bac8eff`) + `parameters/{dev,prod}.bicepparam` | **SUPERSEDED_BY_NEWER** — `main` intentionally ships the smaller standalone baseline per ADR-0002; the larger wave is a future Phase 1 input, not a loss |
| 2 | `container-apps` module (467 lines: API + ETL worker, Key Vault secret-name binding) | `apps/factory.bicep` (133 lines) | **SUPERSEDED_BY_NEWER** — same seam, smaller scope |
| 3 | `storage` module (5 medallion zones, ADLS Gen2) | `storage/blob.bicep` (84 lines, 4 containers) | **SUPERSEDED_BY_NEWER** — zone-count delta is a Phase 1 design input, not missing runtime |
| 4 | `servicebus` + `eventgrid` modules (queue + BlobCreated wiring) | `messaging/servicebus.bicep` (39 lines) + `app/etl/servicebus_consumer.py` (178 lines, dedup + DLQ, tested) | **SUPERSEDED_BY_NEWER** — `main` adds the app-side consumer `03d1f20` lacks |
| 5 | `postgres` module | `database/postgres.bicep` (69 lines) + `app/database/models.py` (`ETLRunManifest`, `QuarantineRecord`) | **SUPERSEDED_BY_NEWER** — `main` adds app models |
| 6 | `identity` + `rbac` modules (UAMI, Contributor scoping) | **absent on `main`** | **STILL_MISSING_ON_MAIN → INTENTIONALLY_DEFERRED** — no managed-identity code exists in `app/` yet; porting IaC without a consumer is Phase 4 scope, not zero-data-loss content |
| 7 | `networking` + `monitoring` modules, `resourceGroups.bicep` | `network/vnet.bicep` (79 lines) + `observability/main.bicep` (32 lines) | **SUPERSEDED_BY_NEWER** — same seams, smaller scope |
| 8 | `keyvault` / `observability` modules | `keyvault/main.bicep` (32 lines) + `observability/main.bicep` | **ALREADY_PRESENT_ON_MAIN** (narrower) |
| 9 | `check_invariants.py` (762 lines, compiled-ARM asserts) + `check_independence.py` + `check-independence.sh` + traversal tests + negative/known-weak fixtures | `check_invariants.py` (181 lines) + `test_checker_traversal.py` (57 lines) + `validate.sh` (90 lines) | **SUPERSEDED_BY_NEWER** — `main` keeps the discipline at reduced coverage; full rule table is Phase 1 hardening input |
| 10 | `iac-validate.yml` (102 lines, self-contained, 8-stage) | `iac-validate.yml` (33 lines) + `ci.yml` (fixture-generate → verify → pytest) + `ci-live.yml` | **SUPERSEDED_BY_NEWER** — `main` CI is green on `a0cd889`; the longer gate is a future input |
| 11 | `CONFIG-CONTRACT.md` + `INFRA-ORIGIN.md` (secret-name binding, bootstrap provenance) | `ROADMAP.md` + `AI-PRODUCTION-GATE.md` + `MCP-RAG-AGENT.md` + ADR-0002 | **CONFLICTING_WITH_CURRENT_ARCHITECTURE** — docs describe the retired tree shape; keeping them alongside `main` docs would fork the source of truth. Rule for port: salvage secret-name binding paragraph into Phase 1/4 docs if still true then |
| 12 | `COMPLETION-MATRIX.md` (as committed in `03d1f20`) | `COMPLETION-MATRIX.md @ a0cd889` (28 rows, Phase 6A–6G gate) | **SUPERSEDED_BY_NEWER** |
| 13 | `app/etl/servicebus_consumer.py` + `tests/test_servicebus_consumer.py` + `ADR-0002` + `AI-PRODUCTION-GATE.md` + `MCP-RAG-AGENT.md` + `ROADMAP.md` + `CURRENT-STATE.md` | — (deleted going `main → ent`) | **PRESENT_ON_MAIN_ONLY** — retiring `ent` preserves all of these |

**Verdict: SAFE TO RETIRE.** No `STILL_MISSING_ON_MAIN` runtime capability is
lost: every deployable seam exists on `main` in narrower form, and the two
genuinely absent pieces (`identity`/`rbac` modules, full invariant rule table)
have no in-app consumer yet — they are **Phase 1/4 future inputs**, explicitly
not ported wholesale per the zero-data-loss rule (old commit targeted baseline
`e5caa2a`, 8 commits behind). MISSING CONTENT PORTED: **NONE**.
`git worktree remove --force /private/tmp/ent-factory` (clean, no untracked) +
`git branch -D ent/enterprise-target` executed; no `origin/ent/*` ever existed.
One-writer state restored: `main` 0 ahead / 0 behind, no second writable
Factory enterprise worktree.
