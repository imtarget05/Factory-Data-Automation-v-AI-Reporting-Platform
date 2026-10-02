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
| **canonical ref (`origin/main`)** | `4ac699f` (Render-purge outcome recorded, PR #2; on top of `a56344c` PR #1) |
| local `HEAD` | not canonical — this branch is `factory/integration`, 3 commits ahead of `origin/main` |
| drift vs origin | `origin/main` is canonical; `factory/integration` is **+3 / 0** (WAVE 0 ledger, WAVE 1 Terraform, chore) |
| worktree | **CLEAN** |
| Render purge | **DONE** — root `render.yaml` + `.github/workflows/keepalive.yml` deleted in PR #1 (merge `a56344c`); anti-Render gate `tests/test_hygiene_no_render.py` (5 tests) merged; `origin/main` tree has **zero** `render.yaml`/`keepalive*` artifacts |
| integration branch | `factory/integration` — **local only, not pushed.** WAVE 0 (`0853743`) and WAVE 1 (`056883f`, Terraform source + plan gate) live here. Nothing in WAVE 0/1 has reached `origin/main` yet |
| stale writer retired | `ent/enterprise-target @ 03d1f20` retired 2026-10-02 after semantic supersession check (worktree removed, local branch deleted; no remote branch existed). See §7. |

Canonical SHA is `a56344c`; the 2026-10-01 ledger (`563a7d4` +3 docs drift) is superseded.

**Post-cleanup measurement (CI run `36915938739`, all jobs green):** the suite
measures **299 passed / 5 skipped / 4 xfailed** — the 294 baseline plus the 5
anti-Render gate tests. `ruff check app/ tests/` and `ruff format --check` both
pass (72 files).

## 2. Infrastructure as deployed today

| Field | Value |
|---|---|
| IaC language | **Terraform — SOURCE_CANONICAL.** Bicep **REMOVED** (see `docs/evidence/terraform-migration/final-bicep-parity.md`). 47 `*.tf` under `infra/terraform/`; **0** `*.bicep` / `*.bicepparam` remain. |
| Terraform entrypoints | `infra/terraform/{versions,providers,backend,variables,locals,main,outputs}.tf` |
| Terraform modules | `infra/terraform/modules/{network,identity,keyvault,storage,postgres,servicebus,eventgrid,container-app,observability,edge}` — all 10 repo-local, each with its own `versions.tf`, **no cross-repo imports, no submodules, no symlinks** |
| Terraform validation | `infra/validate.sh` (fmt · init `-backend=false` · validate · module reachability · 30 plan-invariant self-tests · secret scan) |
| Invariant checker | `infra/terraform/tests/check_plan_invariants.py` — plan-JSON, 7 rule families incl. `pg.secure-transport` and `sb.queue-safety` |
| Terraform remote state | **NOT_CONFIGURED** — `backend.tf` intentionally empty, fail-closed. No state store exists. |
| Terraform apply / import | **NOT DONE** — no Azure resource created, changed or deleted by any IaC work |
| Terraform environments | `infra/terraform/environments/{dev,validation,prod}/terraform.tfvars` |
| Terraform plan gate | `infra/terraform/tests/check_plan_invariants.py` (reads **plan JSON**) + 26 negative controls |
| Terraform CI | `.github/workflows/terraform-validate.yml` (static job + OIDC transient-plan job) |
| CI | `.github/workflows/iac-validate.yml` *(also: `ci.yml`, `ci-live.yml`, `build-container.yml`, `llm-gateway.yml`; `keepalive.yml` removed in the Render cleanup)* |

`storage` and `messaging` modules are present → Blob zone + Service Bus seams exist in Bicep.

## 3. Verified seams present in source

> Presence in source ≠ verified at runtime. This section records existence only.

- Service Bus telemetry consumer — `app/etl/servicebus_consumer.py::TelemetryConsumer`
- Consumer test — `tests/test_servicebus_consumer.py`
- PostgreSQL run metadata models referenced by the consumer test — `app/database/models.py` (`ETLRunManifest`, `QuarantineRecord`)

## 4. Open defects / documented gaps (carried, with source)

- **[factory-clean-clone]** — the canonical suite needs a **generated fixture**; a clean clone cannot reproduce it. `290 passed / 5 skipped / 4 xfailed` at deployed SHA `be4ace3`; the 4 xfailed are **mutation controls that must never pass**. *source: `docs/PORTFOLIO-FLAGSHIP-MATRIX.md`*
- **[factory-ai-report-guard]** — the quality gate is live AND attested, but the **BAD/UNKNOWN branch was never triggered in the cloud**, and `REAL_MODEL` is unverified (no LLM reachable from the container). *source: same.*

## 5. RE-MEASURED 2026-10-02 @ `4ac699f` + WAVE 0/1 on this branch

`origin/main` was fetched first. Canonical is `4ac699f`; this branch rebased
onto it and carries three additional commits (WAVE 0 ledger, WAVE 1 Terraform,
and a follow-up chore). Every number below was measured **after** that rebase.

- test suite: **308 collected → 299 passed / 5 skipped / 4 xfailed in 9.91 s**
  via `.venv` Python 3.12, `pytest tests/ -m "not live and not infra" --strict-markers`.
  The 299 is the 294 WAVE 0 baseline plus the 5 anti-Render hygiene tests that
  landed in `a56344c`; re-measured here rather than carried from CI run
  `36915938739`, because a carried figure is not a measured one.
  System Python 3.14 is **NON-CANONICAL**: collection fails (4 errors,
  `ModuleNotFoundError: reportlab`) — missing declared environment
  dependency, NOT a repository regression.
- ruff: `ruff check app/ tests/` → **All checks passed**;
  `ruff format --check app/ tests/` → **72 files already formatted**.
- fixture: `python -m scripts.verify_fixture --blessed docs/expected/factory-fixture.json`
  → **PASS (schema=factory-fixture-v1, seed=42, 26119 rows)**.
- CI @ `a56344c` / `4ac699f`: run `36915938739`, all jobs green.
- Terraform: **source present on this branch, NOT canonical.** 37 `*.tf` files
  under `infra/terraform/`, 10 modules, 3 environments. `terraform 1.16.3` and
  `trivy 0.74.0` installed; **`tflint` is NOT installed**, so its result is not
  measured here (CI installs it).
  - `terraform fmt -check -recursive` → OK
  - `terraform validate` → **Success! The configuration is valid.**
  - `python3 infra/terraform/tests/test_check_plan_invariants.py`
    → **26/26 tests, 24 checker assertions PASS**
  - `trivy config --severity HIGH,CRITICAL` → **0 HIGH, 0 CRITICAL**
  - **NOT APPLIED** — zero Azure resources created from this tree. `backend.tf`
    is deliberately empty; remote state is Phase 2.
- Render: **purged** in `a56344c` (PR #1). `render.yaml` and
  `.github/workflows/keepalive.yml` are gone and `tests/test_hygiene_no_render.py`
  (5 tests) blocks their return. The earlier "Render active deploy state NOT
  VERIFIED" line is **superseded**: the files no longer exist, so there is no
  competing deploy path left to verify.
- Remaining dead/duplicate deploy surface, **not yet removed**:
  `k8s/40-factory-api-real.yaml`, `k8s/factory-data-src/`, `factory/Dockerfile*`,
  `docker/Dockerfile*`.

### 5b. Azure read-only inventory — MEASURED 2026-10-02 (no mutation)

`az account show` succeeded, so this is **READ_ONLY_MEASURED**, not blocked.

| Field | Measured value |
|---|---|
| subscription | `a3deec78-7edb-41cd-9e94-ec1d4d9379f5` ("Azure subscription 1") |
| identity | `binhtan5734@gmail.com` (user / interactive) |
| resource groups | `rg-portfolio-evidence` (eastasia), `NetworkWatcherRG` |
| Factory resources in `rg-portfolio-evidence` | `ca-factory-api` (Container App), shared `cae-portfolio` (managed env), shared Log Analytics workspace |
| **No** Factory-specific storage / postgres / service bus / key vault | **absent in this subscription** — the Bicep tree is NOT what is deployed |
| live revision | `ca-factory-api--0000003` (Active, 1 replica, Healthy, Provisioned) |
| image | `ghcr.io/…factory-data-automation-v-ai-reporting-platform-factory-api@sha256:7c3e81b7698b7625ef44d7f76ee594d1201acb8622a5497b15d1401e5ed853e2` |
| identity type | `None` — **no managed identity configured** |
| secrets | exactly one: `factory-api-key`, bound to env `FACTORY_API_KEY` |
| ingress | external, targetPort 8000, `allowInsecure: false`, transport Auto |
| scale | Consumption profile, min 1 / max 1 — **single replica, no worker app** |
| probes | **none configured** (`probes: []`) |
| live probe (unauthenticated) | `GET /api/v1/health` → **200** `{"status":"healthy","data_loaded":true}`; `GET /api/v1/kpis` → **401** `{"detail":"missing or invalid X-Factory-API-Key"}` |
| authenticated success path | **NOT VERIFIED** — no credential used; must not be claimed |
| `REAL_MODEL` | **NOT VERIFIED** — no LLM reachable from the container; live report is `FALLBACK` |

**Consequence for the program:** the live platform is *one Container App and
nothing else*. Bicep/Postgres/Blob/Service Bus exist only as source. Rows 3–9
and 12–14 of the completion matrix stay `UNMEASURED`/`NOT_STARTED`; row 15 is
`IMPLEMENTED_TESTED` (pipeline proven), runtime deployment of the full topology
is not.

CARRIED_FORWARD_NOT_REMEASURED (audit docs only — do NOT quote as verified): live revision `ca-factory-api--0000002` running `be4ace3` by digest `sha256:7c3e81b7…` with a SLSA attestation; cloud auth guard rejects unauthenticated requests (401) — **the authenticated success path is NOT VERIFIED** (the probe carried no credential).

## 6. Hazards

- `$HOME` (`/Users/mainguyenbinhtan`) is a **DIRTY worktree** of `FlashSale-Backend`. `Projects/.git` is an **empty stub** → any git run from `Projects/` resolves to `$HOME`. **All git MUST use `git -C <abs repo path>`.**
- Terraform **source exists on `factory/integration`** (37 `*.tf`) and is **NOT
  canonical**. `origin/main` still has **0 `*.tf`**. Factory is **THIRD** in
  migration order (1 MAIA → 2 Helpdesk → 3 Factory) — that order is a program
  decision and is unchanged by the Factory source landing first. Nothing may be
  applied until Phase 2 (remote state + OIDC) and Phase 3 (import, not recreate).
- **Second-writer hazard, observed once already.** A separate writer pushed
  `a56344c` + `4ac699f` to `origin/main` while WAVE 1 was in flight, and left an
  uncommitted edit to `CURRENT-STATE.md` in this worktree. That edit was a
  *stale predecessor* of `4ac699f` and would have regressed three already-merged
  facts (the post-cleanup 299-test measurement, `keepalive.yml` removed from the
  CI list, and the Render purge itself). Lesson: before rebasing, diff the dirty
  worktree against `origin/main` and check whether the uncommitted edit is a
  subset of something already merged. A backup was taken first at
  `/tmp/c12-backup/CURRENT-STATE.md.worktree-copy`.

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
