variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

# Static list, not derived from live endpoints: turning an endpoint on in a
# later apply must also create its DNS zone, not fail on a missing zone.
locals {
  private_dns_zone_names = [
    "privatelink.postgres.database.azure.com",
    "privatelink.blob.core.windows.net",
    "privatelink.file.core.windows.net",
    "privatelink.servicebus.windows.net",
    "privatelink.vaultcore.azure.net",
  ]
}

variable "name_prefix" {
  type        = string
  description = "Short name prefix used to derive the VNet, subnet and private-DNS names."
  default     = "fac"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group holding the network resources."
}

variable "address_space" {
  type        = list(string)
  description = "VNet address space. /16 gives room for the ACA environment subnet, the private-endpoint subnet and future modules without renumbering."
  default     = ["10.20.0.0/16"]
}

variable "aca_subnet_address_prefix" {
  type        = string
  description = "Address prefix for the Container Apps infrastructure subnet. /24 is the Azure minimum for a workload-profile subnet."
  default     = "10.20.0.0/24"
}

variable "private_endpoint_subnet_address_prefix" {
  type        = string
  description = "Address prefix for the private-endpoint subnet. /24 is the Azure minimum for a private-endpoint subnet."
  default     = "10.20.1.0/24"
}

variable "postgres_subnet_address_prefix" {
  type        = string
  description = "Address prefix for the PostgreSQL delegated subnet. Separate from the private-endpoint subnet: a subnet delegated to Microsoft.DBforPostgreSQL/flexibleServers may not also host private endpoints."
  default     = "10.20.2.0/24"
}

variable "deploy_private_endpoints" {
  type        = bool
  description = "Whether private endpoints and their private DNS zones are created. When false the module still creates the VNet and subnets (so the address plan is stable across environments) but creates no private endpoints, and public network access stays on the data-plane resources. The prod environment asserts this is true."
  default     = false
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to every network resource."
  default     = {}
}
