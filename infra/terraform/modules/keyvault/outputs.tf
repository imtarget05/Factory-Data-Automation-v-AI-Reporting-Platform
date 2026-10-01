output "vault_id" {
  description = "Resource id of the vault, used by the container-app module for secret references."
  value       = azurerm_key_vault.this.id
}

output "vault_name" {
  description = "Name of the vault."
  value       = azurerm_key_vault.this.name
}

output "vault_uri" {
  description = "Vault URI. Passed to the container as a non-secret configuration value."
  value       = azurerm_key_vault.this.vault_uri
}

output "private_endpoint_id" {
  description = "Id of the vault private endpoint, or null when private endpoints are disabled."
  value       = try(azurerm_private_endpoint.vault[0].id, null)
}
