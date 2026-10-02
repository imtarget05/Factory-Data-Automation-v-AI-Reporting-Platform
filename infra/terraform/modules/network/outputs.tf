output "vnet_id" {
  description = "Resource id of the VNet."
  value       = azurerm_virtual_network.this.id
}

output "vnet_name" {
  description = "Name of the VNet."
  value       = azurerm_virtual_network.this.name
}

output "container_apps_subnet_id" {
  description = "Subnet id delegated to Microsoft.App/managedEnvironments. The Container Apps module needs this."
  value       = azurerm_subnet.container_apps.id
}

output "private_endpoint_subnet_id" {
  description = "Subnet id that hosts private endpoints, or null when private endpoints are disabled."
  value       = var.deploy_private_endpoints ? azurerm_subnet.private_endpoints.id : null
}

output "postgres_subnet_id" {
  description = "Subnet id delegated to PostgreSQL. Created unconditionally so the address plan is stable across environments, but only referenced when private endpoints are on."
  value       = azurerm_subnet.postgres.id
}

output "private_dns_zone_ids" {
  description = "Map of private DNS zone name to resource id, for the data-plane modules that need to attach one. Empty when private endpoints are disabled."
  value       = { for k, z in azurerm_private_dns_zone.this : k => z.id }
}