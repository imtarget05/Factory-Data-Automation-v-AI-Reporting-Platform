output "account_id" {
  description = "Resource id of the storage account. Referenced by the Event Grid module as the event source."
  value       = azurerm_storage_account.this.id
}

output "account_name" {
  description = "Name of the storage account."
  value       = azurerm_storage_account.this.name
}

output "blob_endpoint" {
  description = "Primary blob data-plane endpoint."
  value       = azurerm_storage_account.this.primary_blob_endpoint
}

output "zone_names" {
  description = "Blob zone (container) names actually created."
  value       = [for c in azurerm_storage_container.zone : c.name]
}

output "system_identity_principal_id" {
  description = "System-assigned identity principal id of the storage account, needed by data-plane role assignments."
  value       = azurerm_storage_account.this.identity[0].principal_id
}

output "private_endpoint_id" {
  description = "Id of the blob private endpoint, or null when private endpoints are disabled."
  value       = try(azurerm_private_endpoint.blob[0].id, null)
}

output "private_endpoint_ip" {
  description = "Private IP of the blob private endpoint, or null when private endpoints are disabled."
  value       = try(azurerm_private_endpoint.blob[0].private_service_connection[0].private_ip_address, null)
}
