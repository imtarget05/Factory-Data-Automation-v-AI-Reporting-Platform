# Final Bicep → Terraform source-parity evidence (Factory)

> **This is a HISTORICAL RECORD, not an active gate.**
> The Bicep stack it describes was deleted in the commit that added this file.
> Nothing here protects the Terraform today. From this point the active
> protection is `infra/validate.sh` (fmt, init, validate, module reachability,
> plan-invariant controls, secret scan). Read this file as a snapshot of what
> was compared, not as a control anyone runs.
>
> It exists because the independent oracle could not be preserved. Helpdesk lost
> its parity checker outright. This file is the deliberate alternative: capture
> the comparison while both sides still exist, so the claim "Terraform matches
> the Bicep it replaced" stays auditable after the Bicep is gone.

## Snapshot point

| Field | Value |
|---|---|
| Canonical pre-delete `main` | `f58672c72defa75740b5f00241d845165aec16d9` |
| Terraform source commit | same (`f58672c`, squash-merge of PR #3) |
| Date captured | 2026-10-02 |
| Tools | Terraform 1.16.3 · azurerm pinned `~> 3.116` |
| Bicep files | **10** |
| Terraform `.tf` files | **47** (10 modules x 4, plus 7 root) |

## What was verified at this point (measured, not asserted)

| Check | Result |
|---|---|
| `terraform fmt -check -recursive` | clean |
| `terraform validate` | Success |
| `terraform init -backend=false` | providers resolved, **no backend contacted** |
| plan-invariant checker self-tests | 26 passed |
| pytest (application) | 299 passed / 5 skipped / 4 xfailed |
| `ruff check` / `ruff format --check` | clean / 72 files formatted |
| Bicep compile (pre-delete) | 8 templates + 2 param files compiled clean |
| `check_invariants.py` on compiled ARM | 8/8 security invariants held |
| `tflint` | **NOT RUN** locally — binary absent; CI ran it in PR #3 |

## Bicep sources (SHA-256, pre-delete)

```text
d283d5b96266dd8b183cdc1100fa06bd39b542a63f1e06c05a59dbb0210fc67c  infra/main.bicep
e2ac458740c72a0e4b4547e8411bf27da7ba959afedc87456724a7a35e3a17b9  infra/modules/apps/factory.bicep
7150dab974c9ee4a6ba710ea9eceb5d1cf86ffcd9d5bd8cbaefa5f3720a6fbd1  infra/modules/database/postgres.bicep
1228e6acf3e5377a2694031fc0ea349b83cdf10fe0c4668e2ba3ac43365ae1d3  infra/modules/keyvault/main.bicep
97e4ac8c12794ee51abbde52e7f39b023e36255b12b04c59bcdea1b9f9219308  infra/modules/messaging/servicebus.bicep
7c86f3ad0ea42d010fa2f4a53057229b9173f0895d00db96f7fe7b904c82231d  infra/modules/network/vnet.bicep
fc967e684ebd81bd825dc694d094cc50b1d1352e41b92bdc27546f708735e084  infra/modules/observability/main.bicep
d25e52a3337d20d516cb8f97c9353087c387b06a9cc7c046f596160adf0ee3f9  infra/modules/storage/blob.bicep
dfefca3e013f94325e981ef9d3136000c6312d781b8aaee67069287bb03621fb  infra/parameters/dev.bicepparam
f56beca322217b916fb1bdbb228a57d2a35303461ffed4fe382c53ffc824ef3e  infra/parameters/prod.bicepparam
```

All ten remain recoverable from git at `f58672c`; the hashes prove this is the
exact tree that was compared.

## Module correspondence

| Bicep | Terraform | Bicep file |
|---|---|---|
## Security invariants: coverage map, and the regression this comparison found

`check_invariants.py` asserted **8** properties on the compiled ARM template.
The Terraform plan-JSON checker covers some. Comparing the two — the one thing
the Bicep oracle was actually for — found a real regression.

| # | Bicep invariant | Terraform equivalent | Covered before this change |
|---|---|---|---|
| 1 | `enablePurgeProtection == True` | `purge_protection_enabled` | yes (`kv.rbac`) |
| 2 | `enableRbacAuthorization == True` | `enable_rbac_authorization` | yes (`kv.rbac`) |
| 3 | `minimumTlsVersion == TLS1_2` | `min_tls_version` | yes (`storage.tls`) |
| 4 | `allowBlobPublicAccess == False` | `allow_nested_items_to_be_public` | yes (`storage.tls`) |
| 5 | `supportsHttpsTrafficOnly == True` | `https_traffic_only_enabled` | yes (`storage.tls`) |
| 6 | `require_secure_transport == 'ON'` | **none** | **NO — regression** |
| 7 | `requiresDuplicateDetection == True` | `requires_duplicate_detection` | **NO — unguarded** |
| 8 | `deadLetteringOnMessageExpiration == True` | `dead_lettering_on_message_expiration` | **NO — unguarded** |

**#6 is a genuine security regression introduced by the port.** The Bicep
PostgreSQL module enforced `require_secure_transport = ON`; the Terraform
`postgres` module declared no `azurerm_postgresql_flexible_server_configuration`
at all, so the control silently stopped existing. Nothing caught it — the parity
tooling compared declarations, not semantics. That is the concrete argument for
keeping a semantic oracle rather than a textual one.

#7 and #8 are not regressions: the Terraform sets both on
`azurerm_servicebus_queue`. They were simply unguarded, so a later edit could
have removed them with no check failing.

**Resolution, in the commit that deletes the Bicep:** #6 restored as an explicit
`azurerm_postgresql_flexible_server_configuration`; #6/#7/#8 added to the
plan-JSON checker with negative controls proving each bites. `check_invariants.py`
and its traversal suite are removed with the Bicep — with nothing to compile they
would be dead executable code creating false confidence.

## Deferred / not proven

| Item | Status |
|---|---|
| `terraform apply` / `import` | **NOT DONE** — no Azure mutation |
| Live parity with the Bicep-provisioned stack | **UNVERIFIED** |
| Remote Terraform state backend | **NOT CONFIGURED** — `backend.tf` intentionally empty, fail-closed |
| `terraform test` contract assertions | **NONE at capture time.** 0 `.tftest.hcl`, so `terraform test` reported `0 passed, 0 failed`. A vacuous success; recorded as a gap, never as a pass. |
| tflint verdict at this SHA | not run locally; CI ran it in PR #3 |
| Entra app / interactive sign-in | absent in both stacks (`azuread` intentionally not required) |

**Do not read this file as evidence that any Azure resource exists.** It records
source equivalence at one commit, and nothing more.
| `modules/apps` | `container-app` | `factory.bicep` |
| `modules/database` | `postgres` | `postgres.bicep` |
| `modules/keyvault` | `keyvault` | `main.bicep` |
| `modules/messaging` | `servicebus` | `servicebus.bicep` |
| `modules/network` | `network` | `vnet.bicep` |
| `modules/observability` | `observability` | `main.bicep` |
| `modules/storage` | `storage` | `blob.bicep` |
| — | `identity` | **no Bicep counterpart** |
| — | `edge` | **no Bicep counterpart** |
| — | `eventgrid` | **no Bicep counterpart** |

The last three are additions, not ports, so they were never parity items.