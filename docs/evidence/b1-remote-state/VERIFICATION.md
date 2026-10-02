# Factory — remote Terraform state foundation (B1)

```text
verified_at : 2026-10-02
status      : REMOTE_BACKEND = VERIFIED_LIVE
```

## What was wrong

This Terraform root had **no backend block at all**, and the `terraform` block
said so explicitly:

```hcl
# Remote state is NOT configured here on purpose. Phase 2 owns the backend
# and requires a repo-owned remote state store; declaring a placeholder would
# let local state files be created and mistaken for durable state.
```

The stated *reason* was right — a placeholder does invite a laptop `.tfstate` to
be mistaken for durable state. But omitting the block entirely did not achieve
it. With no backend block, `terraform init` **succeeds** and the first `apply`
writes state to a laptop. That is the exact failure the comment wanted to
prevent, arrived at by the opposite route, and silently.

The fix is not to omit the block but to make the backend **mandatory and
per-environment**, so a missing `-backend-config` fails closed.

## What exists now

| Field | Value |
|---|---|
| State resource group | `rg-factory-tfstate` (southeastasia, tags project=factory) |
| Storage account | `stfactorystate` (Standard_LRS, StorageV2, TLS1_2) |
| HTTPS only / anonymous blob | `true` / `false` |
| Shared key access | **disabled** (`allowSharedKeyAccess` = null) |
| Container | `tfstate`, reachable with `--auth-mode login`, no account key |
| Operator Blob role | `Storage Blob Data Contributor` @ **storage account** scope |
| Local authoritative state | none |

### Three state keys, one per environment

```
factory/validation.terraform.tfstate   <- the only env CI may apply
factory/dev.terraform.tfstate
factory/prod.terraform.tfstate         <- canonical production state
```

This is the only repository of the three with real `environments/*/terraform.tfvars`
for all three, so all three keys exist. They must stay distinct: CI applies
validation only, and a shared key would let a CI run overwrite a developer's
dev state — or prod's. Probe rule S4 enforces the separation.

## Proof

```text
terraform init -reconfigure -backend-config=environments/validation/backend.hcl
  -> Successfully configured the backend "azurerm"
terraform validate -> Success!

state blob via Blob API (Entra): factory/validation.terraform.tfstate
ls *.tfstate       -> nothing
```

## Plan could NOT be produced — and that is not a state problem

```text
terraform plan -var-file=environments/validation/terraform.tfvars
  -> Error: No value for required variable
       on variables.tf line 26  (tenant_id)
       on variables.tf line 45  (container_image)
```

The backend initialised and `validate` passed. The plan fails on two variables
that **deliberately have no default and no placeholder**:
## Controls

`infra/terraform/tests/probe_backend_isolation.py` — rules S1–S8, each with a
negative control. Here S4 is genuinely exercised: three environments, three
distinct keys.

| Rule | What it prevents |
|---|---|
| S1 | a client secret in the backend path |
| S2 | a storage account key or SAS in any backend config |
| S3 | an environment that does not require Entra auth |
| S4 | two environments sharing one state key |
| S5 | naming another portfolio project's state resources (MAIA's, AKS-SRE's, Helpdesk's) |
| S7 | `use_oidc` hardcoded, which forces the GitHub-only OIDC path and breaks a local `az login` init |
| S8 | a missing backend config silently falling back to local state |

S8 is proven by **running** `terraform init` in a throwaway copy with the
backend config removed and requiring a non-zero exit. It cannot be a grep: the
failure it prevents is the one every other rule stays green through.

## Network and cost

Public network access is **enabled on purpose**: GitHub-hosted runners have no
stable outbound IP to allow-list. Recorded as
`PUBLIC_NETWORK_REACHABLE + ENTRA_AUTH_REQUIRED + SHARED_KEY_DISABLED`, not as
private-endpoint protection.

The storage account **can incur small ongoing cost**. It is **not** a
compute-quota consumer. It is permanent: transient application teardown must
never destroy it.

## CI OIDC

```text
CI_OIDC = NOT_CONFIGURED
```

No GitHub OIDC identity exists for this repository. B1 covered state foundation
only; the backend is already OIDC-compatible, so adding an identity later needs
no config change.

## Bootstrap

```bash
./scripts/bootstrap_state.sh --dry-run          # intent, zero mutation
ALLOW_AZURE_MUTATION=1 ./scripts/bootstrap_state.sh
```

Idempotent. Preflights the storage account name (Azure names are globally
unique) and accepts `allowSharedKeyAccess = null` as disabled, which is how
Azure reports it.

## Not done here

No application resource was created and no `terraform apply` was run. Node,
network, database and messaging sizing are untouched.

- `tenant_id` — "No default and no placeholder: a wrong value must fail loudly,
  not deploy."
- `container_image` — a fully-qualified, digest-pinned OCI reference, with a
  validation rule rejecting a mutable `latest`.

Both are correct refusals by the configuration, not defects. Supplying them is
application-configuration work and requires real inputs (a tenant id and a built
image digest), so it is recorded here rather than faked. Claiming "plan
produced" would have been false.