# COMPLETION MATRIX — Factory-Data-Automation-v-AI-Reporting-Platform

```text
derived_from : docs/enterprise-target/CURRENT-STATE.md
measured_at  : 2026-10-02 @ a0cd8892cb6745751deb89ea8b72a4a5dffb98dd
```

## Status vocabulary

```text
VERIFIED_LIVE       measured on a live Azure runtime; evidence retained
VERIFIED_TRANSIENT  measured in a transient env that was then destroyed; evidence retained
IMPLEMENTED_TESTED  code + tests exist AND a green suite was observed at a frozen SHA
N/A_WITH_EVIDENCE   outside required scope, with a written reason
NOT_STARTED         required; no source exists yet (0 files / absent seam)

INTERIM (must be resolved before Phase 12 freeze — never a terminal state):

IMPLEMENTED_UNVERIFIED  source + tests exist; suite NOT re-run this pass; runtime not verified
UNMEASURED              required; not yet measured in this program
NOT_PASSING             a measured control currently fails
NOT_PRESENT             required; does not exist yet
```

No required row may be closed with `PARTIAL` / `PLANNED_ONLY` / `NOT_VERIFIED`.

## Matrix

| # | Required component | Status (now) | Evidence measured | Close in |
|---|---|---|---|---|
| 1 | Terraform as canonical IaC | **NOT_STARTED** | 0 `*.tf` @ `a0cd889`; Bicep only (migration reference). Factory is 3rd in order (1 MAIA → 2 Helpdesk → 3 Factory) | Phase 1 |
| 2 | Remote state + GitHub OIDC | **NOT_STARTED** | no secretless deploy path measured; no `*.tf`, no backend | Phase 2 |
| 3 | Import existing Azure resources (no recreate) | **UNMEASURED** | live inventory not probed (no mutation attempted) | Phase 3 |
| 4 | VNet + Private Endpoints + Private DNS | **UNMEASURED** | `infra/modules/network/vnet.bicep` (79 lines) + `infra/modules/storage/blob.bicep`; private-endpoint/DNS wiring not measured live | Phase 4 |
| 5 | UAMI + Key Vault | **UNMEASURED** | `infra/modules/keyvault/main.bicep` (32 lines); **no `identity` module on `main`** (retired `03d1f20` identity/rbac is a Phase 4 future input, no in-app consumer yet) | Phase 4 |
| 6 | Blob zones (raw / quarantine / silver / gold / reports) | **UNMEASURED** | `infra/modules/storage/blob.bicep` (84 lines, 4 containers); zone-count delta vs 5-zone enterprise shape is a Phase 1 design input | Phase 5 |
| 7 | PostgreSQL run metadata + quarantine records | **IMPLEMENTED_TESTED** | `app/database/models.py` (`ETLRunManifest`, `QuarantineRecord`); `tests/test_servicebus_consumer.py`; green @ `a0cd889` (294 passed / 5 skipped / 4 xfailed) | Phase 5 |
| 8 | Event Grid → Service Bus → ETL worker + DLQ | **IMPLEMENTED_TESTED** | `app/etl/servicebus_consumer.py` (dedup + DLQ) + `infra/modules/messaging/servicebus.bicep`; green @ `a0cd889` | Phase 5 |
| 9 | Idempotency (duplicate Blob event / duplicate SB message) | **UNMEASURED** | consumer dedup covered by unit tests; duplicate-delivery negative control at runtime not measured | Phase 5 |
| 10 | Deterministic quality gate (fail-closed) | **IMPLEMENTED_TESTED** | `tests/test_ai_quality_gate.py` + `tests/test_ai_quality_mutations.py` (incl. 4 xfailed mutation controls that must never pass); green @ `a0cd889` | Phase 6 |
| 11 | AI report blocked when dataset is CRITICAL | **IMPLEMENTED_TESTED** | gate BAD/UNKNOWN branch covered at unit + HTTP level; **never triggered live in the cloud** (no bad data pushed to prod on purpose) | Phase 6 |
| 12 | Worker restart safety | **UNMEASURED** | — | Phase 6 |
| 13 | OTel + App Insights + Log Analytics + Grafana + SLO | **UNMEASURED** | `infra/modules/observability/main.bicep` (32 lines) + `observability/` (Prometheus 9104 / Grafana 3204); live wiring not measured | Phase 7 |
| 14 | Front Door + WAF + APIM (edge) | **NOT_STARTED** | no `edge`/`apim` module in Bicep; deliberate non-scope per enterprise baseline (API-key auth, Render edge) | Phase 8 |
| 15 | OCI build + SBOM + digest-pinned rollout | **IMPLEMENTED_TESTED** | `build-container.yml` (GHCR push + digest log + SBOM via `anchore/sbom-action` + provenance attestation); **SUCCESS on `a0cd889`** (2026-10-01T17:14:21Z) | Phase 9 |

> Carried live claims (rev `ca-factory-api--0000002` @ `be4ace3` by digest `sha256:7c3e81b7…` with SLSA attestation; 401 guard; quality gate live) are **CARRIED_FORWARD_NOT_REMEASURED**. The BAD/UNKNOWN branch was never triggered in the cloud, and `REAL_MODEL` is unverified.

## AI Production Readiness (Phase 6A–6D)

> Mandatory gate between Phase 6 and Phase 7. Full spec: [`AI-PRODUCTION-GATE.md`](./AI-PRODUCTION-GATE.md). 6B is conditional for Factory.

| # | Required component | Status (now) | Evidence measured | Close in |
|---|---|---|---|---|
| 16 | 6A.1 Provider timeout / retry / fallback / circuit breaker | **UNMEASURED** | `llm-gateway` exists (CB/retry/PII per its README) — no LLM reachable from container | 6A |
| 16b | 6A — Data-quality gate precedes AI report | **IMPLEMENTED_TESTED** | gate suite green @ `a0cd889` (see row 10) | 6A |
| 17 | 6A.3 Structured AI report validation (schema + business) before persist | **IMPLEMENTED_TESTED** | report endpoint returns `generation_mode`/`quality`/`evidence`/`provenance`; green @ `a0cd889` | 6A |
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
