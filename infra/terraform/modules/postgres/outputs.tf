output "server_id" {
  description = "Resource id of the flexible server, used for role assignments and private endpoint creation."
  value       = azurerm_postgresql_flexible_server.this.id
}

output "server_fqdn" {
  description = "Fully-qualified server name. Written into the container as a non-secret configuration value; it carries the host, not the credential."
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

# No identity output. The server is created WITHOUT a system-assigned identity
# in this parity pass: the Entra administrator model needs one, and turning it on
# is part of the Phase 4 identity work together with the role assignments. An
# output that reads a non-existent block would be a plan-time error dressed up as
# a feature.

output "private_endpoint_id" {
  description = "Id of the PostgreSQL private endpoint, or null when private endpoint access is disabled."
  value       = try(azurerm_private_endpoint.postgres[0].id, null)
}
