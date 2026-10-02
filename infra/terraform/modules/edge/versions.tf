terraform {
  # Child modules declare their own constraints. Without this, the module's
  # compatibility is whatever the ROOT happens to pin, so a module that works
  # today silently stops working when the root bumps a provider — and the failure
  # appears in someone else's repository.
  #
  # Duplicated across all ten modules on purpose. A `versions.tf` per module is
  # the Terraform convention; an alternative (a single shared file) would create
  # a cross-directory dependency, which is exactly the coupling the
  # independence rule in this repository forbids.
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.116"
    }
  }
}
