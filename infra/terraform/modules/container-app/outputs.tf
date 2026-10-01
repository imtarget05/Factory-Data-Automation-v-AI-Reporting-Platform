output "environment_id" {
  description = "Resource id of the Container Apps managed environment."
  value       = azurerm_container_app_environment.this.id
}

output "environment_name" {
  description = "Name of the Container Apps managed environment."
  value       = azurerm_container_app_environment.this.name
}

output "app_id" {
  description = "Resource id of the container app."
  value       = azurerm_container_app.this.id
}

output "app_name" {
  description = "Name of the container app."
  value       = azurerm_container_app.this.name
}

output "app_fqdn" {
  description = "Ingress FQDN, or null when ingress is internal. The edge module needs this as its origin."
  value       = try(azurerm_container_app.this.ingress[0].fqdn, null)
}

output "app_identity_principal_id" {
  description = "Principal id of the identity the app runs as, needed for role assignments."
  value       = azurerm_container_app.this.identity[0].principal_id
}

# No client_id output. The app runs as a USER-ASSIGNED identity, whose client id
# belongs to the identity resource in modules/identity, not to the app. The app
# references it; it does not own it. A caller that needs it reads
# module.identity.api_client_id.
