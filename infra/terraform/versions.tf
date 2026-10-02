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

  # Remote state is NOT configured here on purpose. Phase 2 owns the backend
  # and requires a repo-owned remote state store; declaring a placeholder would
  # let local state files be created and mistaken for durable state.
}
