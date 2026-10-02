# Remote state for Factory prod — PARTIAL CONFIG, no credential values.
#
#   terraform init -reconfigure -backend-config=environments/prod/backend.hcl
#
# A DISTINCT key from dev and validation. This is the canonical production state
# and must never be reachable from a CI apply, which is permitted on validation
# only.
#
# `use_azuread_auth = true` and no `use_oidc`; see versions.tf.
resource_group_name  = "rg-factory-tfstate"
storage_account_name = "stfactorystate"
container_name       = "tfstate"
key                  = "factory/prod.terraform.tfstate"

use_azuread_auth = true