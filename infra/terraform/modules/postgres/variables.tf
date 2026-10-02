variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group holding the PostgreSQL server."
}

variable "server_name" {
  type        = string
  description = "PostgreSQL flexible server name. Globally unique, lowercase letters/digits/hyphens."
}

variable "private_endpoint_subnet_id" {
  type        = string
  description = "Subnet id for the private endpoint. Required when create_private_endpoint is true."
  default     = null
}

variable "delegated_subnet_id" {
  type        = string
  description = "Subnet delegated to Microsoft.DBforPostgreSQL/flexibleServers, on which the server itself is placed. Distinct from private_endpoint_subnet_id."
  default     = null
}

# ── The private endpoint ────────────────────────────────────────────────────
# PostgreSQL needs two ids from the caller: the subnet DELEGATED to
# Microsoft.DBforPostgreSQL/flexibleServers (which the server itself lives on)
# and the subnet that HOSTS the private endpoint. They are different subnets and
# cannot be one. The root resolves both from the network module so that no module
# has to know the other's naming.

variable "private_dns_zone_id" {
  type        = string
  description = "Private DNS zone for privatelink.postgres.database.azure.com. Required when private endpoint access is used."
  default     = null
}

variable "sku_name" {
  type        = string
  description = "Compute SKU. Bicep parity: Standard_D2ds_v5 in prod, Standard_B1ms elsewhere."
}


variable "storage_mb" {
  type        = number
  description = "Storage in MB. The run manifest is small; 32 GiB is generous headroom for an audit ledger and cheap at GeneralPurpose pricing."
  default     = 32768
}

variable "server_version" {
  type        = string
  description = "PostgreSQL major version. ADR-0002 specifies v16."
  default     = "16"
}

variable "administrator_login" {
  type        = string
  description = "Entra administrator login name (an Entra object id or name, not a local user)."
}

variable "administrator_password" {
  type        = string
  description = "Password for the legacy administrator path. Nullable on purpose: when null, the server is Entra-admin-only, which is the target state. Supplying it is a documented parity step, not the end state."
  sensitive   = true
  default     = null
}

variable "enable_private_endpoint" {
  type        = bool
  description = "Whether the server is reachable only through a private endpoint. When true, the module requires a delegated subnet id AND a private DNS zone id; the rule is enforced by validation below rather than by an apply-time error."
  default     = false

  validation {
    condition     = !var.enable_private_endpoint || (var.delegated_subnet_id != null && var.private_dns_zone_id != null)
    error_message = "enable_private_endpoint requires both delegated_subnet_id and private_dns_zone_id. A private-access server with no delegated subnet cannot be created, and one with no private DNS zone resolves no hostname."
  }
}


variable "high_availability_enabled" {
  type        = bool
  description = "Zone-redundant HA. Only meaningful in prod, where losing the run-manifest store means losing the audit ledger."
  default     = false
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to the server."
  default     = {}
}
