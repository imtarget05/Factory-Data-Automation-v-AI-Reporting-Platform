# COMPLETION MATRIX — Factory-Data-Automation-v-AI-Reporting-Platform

```text
derived_from : docs/enterprise-target/CURRENT-STATE.md
measured_at  : 2026-10-02 @ 4ac699f (canonical) + factory/integration (WAVE 0/1)
```

## Status vocabulary

```text
VERIFIED_LIVE       measured on a live Azure runtime; evidence retained
VERIFIED_TRANSIENT  measured in a transient env that was then destroyed; evidence retained
IMPLEMENTED_TESTED  code + tests exist AND a green suite was observed at a frozen SHA
N/A_WITH_EVIDENCE   outside required scope, with a written reason
NOT_STARTED         required; no source exists yet (0 files / absent seam)

INTERIM (must be resolved before Phase 12 freeze — never a terminal state):

SOURCE_PARITY_VERIFIED  Terraform source exists, validates, and its security gate
                        bites — but it is NOT canonical and nothing is deployed
IMPLEMENTED_UNVERIFIED  source + tests exist; suite NOT re-run this pass; runtime not verified
UNMEASURED              required; not yet measured in this program
NOT_PASSING             a measured control currently fails
NOT_PRESENT             required; does not exist yet
```

No required row may be closed with `PARTIAL` / `PLANNED_ONLY` / `NOT_VERIFIED`.

## Matrix

| # | Required component | Status (now) | Evidence measured | Close in |
|---|---|---|---|---|
| 1 | Terraform as canonical IaC | **SOURCE_PARITY_VERIFIED** (not canonical) | 37 `*.tf` under `infra/terraform/` on `factory/integration`; `terraform validate` Success; `fmt -check` OK; 26/26 plan-gate negative controls PASS; trivy 0 HIGH/CRITICAL. **`origin/main` still has 0 `*.tf`** and nothing is applied. Factory is 3rd in order (1 MAIA → 2 Helpdesk → 3 Factory). Parity: `TERRAFORM-PARITY-MATRIX.md` | Phase 1→3 |
| 2 | Remote state + GitHub OIDC | **NOT_STARTED** | `backend.tf` is deliberately EMPTY (a placeholder would let a local tfstate be mistaken for durable state). CI plan job uses `azure/login` OIDC with **no `AZURE_CLIENT_SECRET`**, but it is unproven against a real plan | Phase 2 |
| 3 | Import existing Azure resources (no recreate) | **UNMEASURED** | inventory measured 2026-10-02: only `ca-factory-api` + shared `cae-portfolio` + shared LAW in `rg-portfolio-evidence`; no import executed | Phase 3 |
| 4 | VNet + Private Endpoints + Private DNS | **SOURCE_PARITY_VERIFIED** (not deployed) | Bicep `infra/modules/network/vnet.bicep`; Terraform `modules/network` (VNet, ACA subnet, PE subnet, PG subnet, 5 private DNS zones) + per-resource private endpoints. **No VNet in the live subscription** | Phase 4 |
| 5 | UAMI + Key Vault | **SOURCE_PARITY_VERIFIED** (not deployed) | Terraform `modules/identity` (api read-only + worker UAMI) and `modules/keyvault` (RBAC, purge protection, 90-day soft delete). **Role assignments are DEFERRED** — the identities exist and are inert. Live ACA `identity.type = None`; no Key Vault in Azure | Phase 4 |
| 6 | Blob zones (raw / quarantine / silver / gold / reports) | **SOURCE_PARITY_VERIFIED** (not deployed) | Bicep defines 4 zones (no `reports`); Terraform defines the full **5** (raw-landing, quarantine-corrupt, silver-clean, gold-marts, reports) + versioning + blob/container soft delete. **No storage account in Azure** | Phase 5 |
| 7 | PostgreSQL run metadata + quarantine records | **IMPLEMENTED_TESTED** | `app/database/models.py` (`ETLRunManifest`, `QuarantineRecord`); `tests/test_servicebus_consumer.py`; green @ `4ac699f` (299 passed / 5 skipped / 4 xfailed). **Not deployed** — no Postgres in Azure | Phase 5 |
| 8 | Event Grid → Service Bus → ETL worker + DLQ | **IMPLEMENTED_TESTED** (app) + **SOURCE_PARITY_VERIFIED** (IaC) | app: `app/etl/servicebus_consumer.py` (dedup + DLQ), green @ `4ac699f`-era. IaC: Terraform `modules/servicebus` (explicit DLQ, dedup PT10M) + `modules/eventgrid` (BlobCreated → queue, UAMI-authenticated) — **ahead of Bicep, which had no Event Grid**. **Not deployed**: no Service Bus / Event Grid in Azure, and **no ETL worker container app exists** (deferred: no worker entry point in `app/`) | Phase 5 |
| 9 | Idempotency (duplicate Blob event / duplicate SB message) | **UNMEASURED** | consumer dedup covered by unit tests; duplicate-delivery negative control at runtime not measured | Phase 5 |
| 10 | Deterministic quality gate (fail-closed) | **IMPLEMENTED_TESTED** | `tests/test_ai_quality_gate.py` + `tests/test_ai_quality_mutations.py` (incl. 4 xfailed mutation controls that must never pass); green @ `4ac699f` (299 passed / 5 skipped / 4 xfailed) | Phase 6 |
| 11 | AI report blocked when dataset is CRITICAL | **IMPLEMENTED_TESTED** | gate BAD/UNKNOWN branch covered at unit + HTTP level; **never triggered live in the cloud** (no bad data pushed to prod on purpose) | Phase 6 |
| 12 | Worker restart safety | **NOT_STARTED** | no ETL worker process exists in source or runtime (consumer is a library seam only) | Phase 6 |
| 13 | OTel + App Insights + Log Analytics + Grafana + SLO | **UNMEASURED** | Terraform `modules/observability` (workspace, App Insights workspace-based, action group, 4 alert rules each naming a runbook) + local `observability/` (Prometheus 9104 / Grafana 3204). Live ACA has **no probes** and no verified App Insights wiring | Phase 7 |
| 14 | Front Door + WAF + APIM (edge) | **SOURCE_PARITY_VERIFIED** (not deployed, not enabled) | Terraform `modules/edge` (Front Door Premium, WAF `Prevention`, APIM Consumption + API-level rate-limit policy) — **absent in Bicep entirely**. `enable_edge = false` ⇒ `count = 0` ⇒ the plan contains **zero** edge resources. Not applied | Phase 8 |
| 15 | OCI build + SBOM + digest-pinned rollout | **IMPLEMENTED_TESTED** | `build-container.yml` (GHCR push + digest log + SBOM via `anchore/sbom-action` + provenance attestation); **SUCCESS on `a0cd889`** (run `36897901007`). Terraform independently enforces digest-pinning: `container_image` is validated to match `@sha256:<64 hex>`, so a mutable tag cannot reach a plan | Phase 9 |

> Carried live claims (rev `ca-factory-api--0000002` @ `be4ace3` by digest `sha256:7c3e81b7…` with SLSA attestation; 401 guard; quality gate live) are **CARRIED_FORWARD_NOT_REMEASURED**. The BAD/UNKNOWN branch was never triggered in the cloud, and `REAL_MODEL` is unverified.

## AI Production Readiness (Phase 6A–6D)

> Mandatory gate between Phase 6 and Phase 7. Full spec: [`AI-PRODUCTION-GATE.md`](./AI-PRODUCTION-GATE.md). 6B is conditional for Factory.

| # | Required component | Status (now) | Evidence measured | Close in |
|---|---|---|---|---|
| 16 | 6A.1 Provider timeout / retry / fallback / circuit breaker | **UNMEASURED** | `llm-gateway` exists (CB/retry/PII per its README) — no LLM reachable from container | 6A |
| 16b | 6A — Data-quality gate precedes AI report | **IMPLEMENTED_TESTED** | gate suite green @ `4ac699f` (299 passed / 5 skipped / 4 xfailed) (see row 10) | 6A |
| 17 | 6A.3 Structured AI report validation (schema + business) before persist | **IMPLEMENTED_TESTED** | report endpoint returns `generation_mode`/`quality`/`evidence`/`provenance`; green @ `4ac699f` (299 passed / 5 skipped / 4 xfailed) | 6A |
| 18 | 6A.6 No secrets in prompt / log / metric / trace | **UNMEASURED** | — | 6A |
| 19 | 6B Multi-agent safety | **N/A_WITH_EVIDENCE** *(conditional)* | applies only if genuine agent orchestration exists | 6B |
| 20 | 6C.1 Bounded concurrency | **UNMEASURED** | — | 6C |
| 21 | 6C.5 AI cost metrics | **UNMEASURED** | — | 6C |
| 22 | 6D.1 Golden dataset (report quality) | **UNMEASURED** | — | 6D |
| 23 | 6D.4 Slice-level regression gate | **UNMEASURED** | — | 6D |
| 24 | Phase 7 AI distributed tracing | **UNMEASURED** | `infra/modules/observability` | 7 |

## MCP + RAG + Agent (Phase 6E–6G)

> Full spec: [`MCP-RAG-AGENT.md`](./MCP-RAG-AGENT.md). Factory identity: **Deterministic Data Platform + MCP-connected AI Investigation Agent**.

| # | Required component | Status (now) | Evidence measured | Close in |
|---|---|---|---|---|
| 25 | 6E SOP / manual RAG (supporting; never a quality gate) | **UNMEASURED** | — | 6E |
| 26 | 6F MCP platform (KPI / batch / quality / lineage / document / job) | **UNMEASURED** | — | 6F |
| 27 | 6F `job.reprocess` behind authz + idempotency + Service Bus | **UNMEASURED** | — | 6F |
| 28 | 6G Agent + RAG + MCP E2E (deterministic gate precedes agent) | **UNMEASURED** | — | 6G |
