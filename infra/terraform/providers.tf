provider "azurerm" {
  # Subscription comes from TF_VAR_subscription_id (never committed).
  features {
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

# No provider block for `azuread`: see versions.tf.
