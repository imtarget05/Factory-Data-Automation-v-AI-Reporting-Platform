# Remote state for Factory dev — PARTIAL CONFIG, no credential values.
#
#   terraform init -reconfigure -backend-config=environments/dev/backend.hcl
#
# A DISTINCT key from validation and prod. Environments must never share a state
# file: CI applies only validation, so a shared key would let a CI run overwrite
# a developer's dev state, and a typo could take prod's state with it.
#
# `use_azuread_auth = true` and no `use_oidc`; see versions.tf.
resource_group_name  = "rg-factory-tfstate"
storage_account_name = "stfactorystate"
container_name       = "tfstate"
key                  = "factory/dev.terraform.tfstate"

use_azuread_auth = true