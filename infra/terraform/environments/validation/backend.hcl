# Remote state for Factory validation — PARTIAL CONFIG, no credential values.
#
#   terraform init -reconfigure -backend-config=environments/validation/backend.hcl
#
# This repository's OWN state identity, sharing nothing with MAIA, AKS-SRE or
# Helpdesk. Validation is the only environment CI is permitted to apply.
#
# `use_azuread_auth = true` and no `use_oidc`; see versions.tf for why a static
# OIDC flag is wrong for a shared, committed config.
resource_group_name  = "rg-factory-tfstate"
storage_account_name = "stfactorystate"
container_name       = "tfstate"
key                  = "factory/validation.terraform.tfstate"

use_azuread_auth = true