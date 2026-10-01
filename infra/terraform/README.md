# infra/terraform — Factory Azure infrastructure (Terraform)

> **Status: source parity. Not canonical yet.** Bicep under `infra/` remains the
> migration reference until the parity matrix below is complete and Phase 1
> closes. See `docs/enterprise-target/TERRAFORM-PARITY-MATRIX.md`.

## What this is

The Terraform implementation of the Factory platform: a deterministic data
platform on Azure — Blob medallion zones, Event Grid ingestion trigger, Service
Bus queue with duplicate detection and a dead-letter queue, PostgreSQL run
manifest store, Key Vault, a Container Apps API behind a user-assigned managed
identity, and an optional edge (Front Door Premium + WAF + APIM).

## What this is not

It deploys nothing by itself. `backend.tf` is intentionally empty: remote state
is Phase 2, and an empty backend block is the fail-closed choice, because a
placeholder would let a local `terraform.tfstate` be created and mistaken for
durable state.

## Layout

```text
infra/terraform/
├── versions.tf          pinned Terraform + provider, no backend
├── providers.tf         azurerm features (resource-group + key-vault guards)
├── backend.tf           deliberately empty — see above
├── variables.tf         every input, with the production invariants enforced
├── locals.tf            one name map, one private-endpoint switch, alert rules
├── main.tf              wiring order only; no resource policy lives here
├── outputs.tf           ids and hostnames the next phase needs
├── modules/
│   ├── network/         VNet, ACA subnet, private-endpoint subnet, PG subnet, DNS zones
│   ├── identity/        two UAMIs: api (read-only) and worker (write)
│   ├── keyvault/        vault, RBAC on, purge protection on, private endpoint
│   ├── storage/         ADLS Gen2 account, five medallion zones, blob endpoint
│   ├── postgres/        flexible server v16, HA in prod, private endpoint
│   ├── servicebus/      namespace, telemetry queue, explicit DLQ, private endpoint
│   ├── eventgrid/       BlobCreated -> queue, authenticated by UAMI
│   ├── container-app/   managed environment + API app with probes
│   ├── observability/   Log Analytics, App Insights, action group, alert rules
│   └── edge/            Front Door Premium, WAF, APIM (not instantiated by default)
├── environments/        dev | validation | prod committed tfvars
├── tests/
│   ├── check_plan_invariants.py        fail-closed plan checker
│   └── test_check_plan_invariants.py   negative controls for the checker
└── .trivyignore         documented scanner suppressions
```

## The three gates

1. **`terraform validate`** proves the configuration is well-formed. It does not
   prove the plan is safe.
2. **`tests/check_plan_invariants.py`** reads the *plan JSON* — the artefact that
   would actually be sent to Azure — and asserts security properties on it: TLS
   1.2, no public blob access, RBAC + purge protection on the vault, digest-pinned
   images, probes present, secrets bound by reference and never as plain env
   values, closed public data plane in prod, an action group that exists, alerts
   that name a runbook, and a real `source_sha` tag. It **fails closed**: an
   unreadable plan, a missing resource, or a rule that raises is a failure, never
   a pass.
3. **`tests/test_check_plan_invariants.py`** mutates one property at a time and
   asserts the checker fails *for that reason*. 26 tests, 24 checker assertions.
   Without this, a checker that silently stopped matching would let every later
   plan through and CI would be green exactly when it matters least.

## Commands

```bash
cd infra/terraform

terraform init -backend=false -input=false
terraform validate
terraform fmt -check -recursive

# plan against the transient validation environment (needs Azure credentials)
terraform plan -out=tfplan -var-file=environments/validation/terraform.tfvars
terraform show -json tfplan > plan.json
python3 tests/check_plan_invariants.py plan.json --environment validation

# the checker's own negative controls (no network, no credentials)
python3 tests/test_check_plan_invariants.py
```

## What is deliberately NOT here yet

| Missing | Why | Phase |
|---|---|---|
| remote state backend | no repo-owned store exists; a local state file is not durable state | 2 |
| `azuread` provider / OIDC federation | nothing in `app/` validates an Entra token; adding the provider now is an unused dependency | 2 |
| role assignments for the UAMIs | the identities exist and are inert; grants are a separate, reviewable file | 4 |
| the ETL worker container app | no worker entry point exists in `app/`, so the container would crash-loop on a missing command | 2 (WAVE 2) |
| `terraform test` (.tftest.hcl) | needs a real plan; the plan-based gate above covers the same ground sooner | 2 |
| `tflint` in local dev | installed in CI; not present on this machine | — |

A resource is absent from this tree because something does not exist to deploy
it, not because it was forgotten. The table is the honest reason for each.

## Secrets

No secret value is ever declared in this tree. The vault is created empty; values
are written out of band; Terraform tracks the *reference*. `tenant_id`,
`container_image` and `postgres_administrator_password` arrive as `TF_VAR_*`, and
the last one should be `null` in the target state (Entra-only administration).

`container_image` is validated to be digest-pinned. A tag — including `latest` —
is rejected at plan time, so a mutable reference cannot reach an apply.
