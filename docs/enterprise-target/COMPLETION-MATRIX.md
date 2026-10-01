# COMPLETION MATRIX — Factory-Data-Automation-v-AI-Reporting-Platform

```text
derived_from : docs/enterprise-target/CURRENT-STATE.md
measured_at  : 2026-10-01
```

## Status vocabulary

```text
VERIFIED_LIVE       measured on a live Azure runtime; evidence retained
VERIFIED_TRANSIENT  measured in a transient env that was then destroyed; evidence retained
IMPLEMENTED_TESTED  code + tests exist AND a green suite was observed at a frozen SHA
N/A_WITH_EVIDENCE   outside required scope, with a written reason

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
| 1 | Terraform as canonical IaC | **NOT_PRESENT** | 0 `*.tf`; Bicep only | Phase 1 |
| 2 | Remote state + GitHub OIDC | **NOT_PRESENT** | no secretless deploy path measured | Phase 2 |
| 3 | Import existing Azure resources (no recreate) | **UNMEASURED** | live inventory not probed | Phase 3 |
| 4 | VNet + Private Endpoints + Private DNS | **UNMEASURED** | `infra/modules/network`, `storage` | Phase 4 |
| 5 | UAMI + Key Vault | **UNMEASURED** | `infra/modules/keyvault` (no `identity` module today) | Phase 4 |
| 6 | Blob zones (raw / quarantine / silver / gold / reports) | **UNMEASURED** | `infra/modules/storage` | Phase 5 |
| 7 | PostgreSQL run metadata + quarantine records | **IMPLEMENTED_UNVERIFIED** | `app/database/models.py`; `tests/test_servicebus_consumer.py` | Phase 5 |
| 8 | Event Grid → Service Bus → ETL worker + DLQ | **IMPLEMENTED_UNVERIFIED** | `app/etl/servicebus_consumer.py`; `infra/modules/messaging` | Phase 5 |
| 9 | Idempotency (duplicate Blob event / duplicate SB message) | **UNMEASURED** | — | Phase 5 |
| 10 | Deterministic quality gate (fail-closed) | **IMPLEMENTED_UNVERIFIED** | 19 regression tests incl. negative control (audit) | Phase 6 |
| 11 | AI report blocked when dataset is CRITICAL | **IMPLEMENTED_UNVERIFIED** | — | Phase 6 |
| 12 | Worker restart safety | **UNMEASURED** | — | Phase 6 |
| 13 | OTel + App Insights + Log Analytics + Grafana + SLO | **UNMEASURED** | `infra/modules/observability` | Phase 7 |
| 14 | Front Door + WAF + APIM (edge) | **UNMEASURED** | no `edge`/`apim` module in Bicep today | Phase 8 |
| 15 | OCI build + SBOM + digest-pinned rollout | **UNMEASURED** | `build-container.yml` | Phase 9 |

> Carried live claims (rev `ca-factory-api--0000002` @ `be4ace3` by digest `sha256:7c3e81b7…` with SLSA attestation; 401 guard; quality gate live) are **CARRIED_FORWARD_NOT_REMEASURED**. The BAD/UNKNOWN branch was never triggered in the cloud, and `REAL_MODEL` is unverified.

## AI Production Readiness (Phase 6A–6D)

> Mandatory gate between Phase 6 and Phase 7. Full spec: [`AI-PRODUCTION-GATE.md`](./AI-PRODUCTION-GATE.md). 6B is conditional for Factory.

| # | Required component | Status (now) | Evidence measured | Close in |
|---|---|---|---|---|
| 16 | 6A.1 Provider timeout / retry / fallback / circuit breaker | **UNMEASURED** | `llm-gateway` exists (CB/retry/PII per its README) — no LLM reachable from container | 6A |
| 16b | 6A — Data-quality gate precedes AI report | **IMPLEMENTED_UNVERIFIED** | 19 regression tests incl. negative control (audit) | 6A |
| 17 | 6A.3 Structured AI report validation (schema + business) before persist | **IMPLEMENTED_UNVERIFIED** | report endpoint returns `generation_mode`/`quality`/`evidence`/`provenance` | 6A |
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
