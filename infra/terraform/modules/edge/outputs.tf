output "firewall_policy_id" {
  description = "Id of the WAF policy."
  value       = azurerm_cdn_frontdoor_firewall_policy.this.id
}

output "profile_id" {
  description = "Id of the Front Door profile."
  value       = azurerm_cdn_frontdoor_profile.this.id
}

output "endpoint_id" {
  description = "Id of the Front Door endpoint."
  value       = azurerm_cdn_frontdoor_endpoint.this.id
}

output "endpoint_hostname" {
  description = "Public hostname of the Front Door endpoint. This is the address clients should use, not the Container App FQDN."
  value       = azurerm_cdn_frontdoor_endpoint.this.host_name
}

output "api_management_id" {
  description = "Id of the API Management service."
  value       = azurerm_api_management.this.id
}

output "api_management_gateway_url" {
  description = "Public gateway URL of the API Management service."
  value       = azurerm_api_management.this.gateway_url
}