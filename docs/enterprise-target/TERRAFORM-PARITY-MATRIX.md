# TERRAFORM PARITY MATRIX — Bicep → Terraform

> **This matrix is the definition of "Terraform source parity".** A row may only
> be marked `PORTED` when the Terraform resource exists, is wired in `main.tf`,
> and is asserted by `infra/terraform/tests/check_plan_invariants.py`. A row
> marked `DEFERRED` has no Terraform source, and saying otherwise is the
> overclaim this repository's evidence rules forbid.
>
> Bicep reference: `infra/` at `be2fb04`. Terraform: `infra/terraform/` on
> branch `factory/tf`. Measured 2026-10-02.

## Legend

| Status | Meaning |
|---|---|
| `PORTED` | Exists in Terraform, wired, property asserted on the plan |
| `PORTED_EXTENDED` | Ported, plus an intentional addition the Bicep baseline lacked — the addition is named |
| `NARROWER` | Ported but deliberately smaller than Bicep; the gap and its phase are named |
| `DEFERRED` | No Terraform source. An absence with a reason, not work in progress |
| `ABSENT_IN_BICEP` | Present in Terraform, absent in Bicep |

## Platform

| Bicep resource | Terraform resource | Status | Notes |
|---|---|---|---|
| RG scope, group created out of band | `azurerm_resource_group.this` | `PORTED` | Terraform owns the group so state is complete |
| `Microsoft.KeyVault/vaults` | `azurerm_key_vault.this` | `PORTED` | RBAC, purge protection, 90-day soft delete, private endpoint in prod |
| `Microsoft.OperationalInsights/workspaces` | `azurerm_log_analytics_workspace.this` | `PORTED` | + daily quota (cost control Bicep lacked) |
| `Microsoft.Insights/components` | `azurerm_application_insights.this` | `PORTED` | workspace-based, so trace/log correlate |
| — | `azurerm_monitor_action_group.this` | `PORTED_EXTENDED` | Bicep had none. Four alert rules, each naming a runbook |
| — | `azurerm_monitor_metric_alert.this` | `PORTED_EXTENDED` | Bicep had none |

## Data plane

| Bicep resource | Terraform resource | Status | Notes |
|---|---|---|---|
| `Microsoft.Storage/storageAccounts` | `azurerm_storage_account.this` | `PORTED` | TLS 1.2, HTTPS-only, no public blob, 14-day soft delete, versioning, GRS in prod |
| 4 blob containers | `azurerm_storage_container.zone` ×5 | `PORTED_EXTENDED` | **5 zones, not 4.** Bicep had no `reports`; the exporter persists Excel/PDF and needs a durable home |
| — | `azurerm_private_endpoint.blob` | `PORTED_EXTENDED` | Bicep had none |
| `Microsoft.ServiceBus/namespaces` | `azurerm_servicebus_namespace.this` | `PORTED` | TLS 1.2 |
| `queues/factory-telemetry-inbox` | `azurerm_servicebus_queue.telemetry` | `PORTED` | dedup PT10M, maxDeliveryCount 10, TTL P14D |
| implicit DLQ | `azurerm_servicebus_queue.telemetry_dead_letter` | `PORTED_EXTENDED` | declared so its settings are reviewable and the replay runbook has a named target |
| — | `azurerm_private_endpoint.servicebus` | `PORTED_EXTENDED` | Bicep had none |
| `Microsoft.DBforPostgreSQL` | `azurerm_postgresql_flexible_server.this` | `PORTED` | v16, GRS + zone-redundant HA in prod, 7-day backup |
| — | `azurerm_private_endpoint.postgres` | `PORTED_EXTENDED` | Bicep had none |


## Apps

| Bicep resource | Terraform resource | Status | Notes |
|---|---|---|---|
| `Microsoft.App/managedEnvironments` | `azurerm_container_app_environment.this` | `PORTED` | Consumption profile: flat attributes, not `vnet_configuration` |
| `Microsoft.App/containerApps` (api) | `azurerm_container_app.this` | `PORTED` | **probes added** — the live app has `probes: []`; digest-pinned image; secrets by reference |
| container secrets | `azurerm_container_app.secret` ×N | `PORTED` | secret name = env var name, so no second mapping can drift |
| — | ETL worker container app | `DEFERRED` | No worker entry point in `app/`; a container with no command crash-loops. WAVE 2 |
| — | UAMI role assignments | `DEFERRED` | Identities are created and inert. Grants belong in a separate reviewable file, Phase 4 |

## Network

| Bicep resource | Terraform resource | Status | Notes |
|---|---|---|---|
| `Microsoft.Network/virtualNetworks` | `azurerm_virtual_network.this` | `PORTED` | |
| ACA subnet | `azurerm_subnet.container_apps` | `PORTED` | delegation → `Microsoft.App/environments` |
| second subnet | `azurerm_subnet.private_endpoints` | `PORTED_EXTENDED` | no delegation: a PE subnet serves many targets |
| — | `azurerm_subnet.postgres` | `PORTED_EXTENDED` | **new and necessary.** A private-access PG server needs its own delegated subnet and cannot share the PE subnet |
| — | `azurerm_private_dns_zone.this` ×5 | `PORTED_EXTENDED` | Bicep had no private DNS at all |

## Ingestion trigger

| Bicep resource | Terraform resource | Status | Notes |
|---|---|---|---|
| — (Bicep had no Event Grid) | `azurerm_eventgrid_topic.this` | `ABSENT_IN_BICEP` | ADR-0002 specifies BlobCreated → Service Bus; Bicep never implemented it |
| — | `azurerm_eventgrid_event_subscription.blob_to_servicebus` | `ABSENT_IN_BICEP` | filtered to `raw-landing` + `quarantine-corrupt`; delivery authenticated by the worker UAMI, no access key |

The subject filter is the load-bearing detail. A subscription on the whole
storage account would also fire on silver/gold/reports writes, and the pipeline
would trigger itself in a loop.

## Edge

| Bicep resource | Terraform resource | Status | Notes |
|---|---|---|---|
| — | `azurerm_cdn_frontdoor_profile.this` | `ABSENT_IN_BICEP` | module exists, `enable_edge = false` |
| — | `azurerm_cdn_frontdoor_firewall_policy.this` | `ABSENT_IN_BICEP` | `mode = Prevention`, not Detection |
| — | `azurerm_cdn_frontdoor_endpoint.this` | `ABSENT_IN_BICEP` | |
| — | `azurerm_api_management.this` + API + rate-limit policy | `ABSENT_IN_BICEP` | Consumption SKU; rate limit is a placeholder pending a traffic baseline |

`count = var.enable_edge ? 1 : 0`, so a disabled edge yields **zero** edge
resources in the plan rather than a disabled placeholder. A module that exists
and is not instantiated is the honest form of "we know what the edge requires".

## Cross-cutting

| Concern | Bicep | Terraform | Status |
|---|---|---|---|
| invariant checker | `infra/check_invariants.py` (181 lines, AST on `.bicep` source) | `tests/check_plan_invariants.py` (reads **plan JSON**) | `PORTED_EXTENDED` — reads the applied artefact, not the source, so source/plan divergence cannot fool it |
| negative controls | `infra/scripts/test_checker_traversal.py` (57 lines) | `tests/test_check_plan_invariants.py` (26 tests, 24 assertions) | `PORTED_EXTENDED` |
| validation | `infra/validate.sh` (90 lines) | `.github/workflows/terraform-validate.yml` (fmt/init/validate/tflint/trivy/controls + credentialed plan) | `PORTED` |
| independence check | none | none | `DEFERRED` — a per-repo tree with no cross-repo module has nothing to check; a checker that passes trivially is worse than none |
| secret scan | `validate.sh` step 5 | trivy config + the `app.hardened` plain-env rule | `PORTED` |

## Verdict

**TERRAFORM SOURCE PARITY = VERIFIED for every resource the Bicep baseline
contains.** Two categories are honestly open, and both are absences rather than
half-finished work:

- `DEFERRED` — worker app, role assignments: nothing to deploy yet.
- `ABSENT_IN_BICEP` — Event Grid, private DNS, private endpoints, edge: the
  Terraform tree is *ahead* of the Bicep baseline here, which is the point of
  Phase 1, but it also means parity is a floor, not a ceiling.

**Not yet true, and not claimed:** Terraform is not canonical IaC. That needs
Phase 2 (remote state + OIDC) and Phase 3 (import the existing `ca-factory-api`
without recreating it). A green `terraform validate` is not evidence that any
resource exists — as of 2026-10-02 **nothing in this tree has been applied**.
