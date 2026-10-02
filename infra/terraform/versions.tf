terraform {
  # Pinned. `.terraform.lock.hcl` is committed; `.terraform/`, `*.tfstate*`
  # and `*.tfplan` are gitignored (see .gitignore at repo root).
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.116"
    }
    # azuread is intentionally NOT required yet. No Entra application
    # registration is provisioned because nothing in `app/` validates an
    # Entra-issued token (Factory authenticates with a shared API key compared
    # at the app, app/api/security.py). Adding the provider now would create
    # an unused dependency. Phase 2 (GitHub OIDC) is where it becomes required.
  }

  # Remote state IS configured here, as PARTIAL configuration. The previous
  # comment said "not configured on purpose" — the reasoning (a placeholder would
  # let local state files be mistaken for durable state) was right, but leaving
  # the block absent did not achieve it: with no backend block at all,
  # `terraform init` succeeds and writes state to a laptop `.tfstate`. The fix
  # is not to omit the block but to make the backend MANDATORY and per-
  # environment, so a missing `-backend-config` fails closed.
  #
  # Authentication is Entra ID only and is per-environment:
  #     local : `az login` (use_azuread_auth = true in backend.hcl)
  #     CI    : ARM_USE_OIDC=true ARM_USE_AZUREAD_AUTH=true + ARM_CLIENT_ID /
  #             ARM_TENANT_ID / ARM_SUBSCRIPTION_ID
  #
  # `use_oidc` is deliberately NOT committed here or in any backend.hcl: a
  # static value forces the GitHub Actions OIDC path, which reads
  # ACTIONS_ID_TOKEN_REQUEST_TOKEN and therefore breaks a local `az login` init.
  # tests/probe_backend_isolation.py fails the build if it is hardcoded back.
  #
  # State identity is this repository's own. See docs/evidence/b1-remote-state/.
  backend "azurerm" {}
}
