variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

variable "tenant_id" {
  type        = string
  description = "Microsoft Entra tenant id that owns the vault. No default: a wrong tenant produces a vault in the wrong directory, which is exactly the failure a placeholder would hide."
}

variable "resource_group_name" {
  type        = string
  description = "Resource group holding the vault. Passed in, not created here."
}

variable "vault_name" {
  type        = string
  description = "Key Vault name. 3-24 alphanumeric and hyphen characters, globally unique, no trailing hyphen."

  validation {
    condition     = can(regex("^[A-Za-z0-9-]{3,24}$", var.vault_name)) && !endswith(var.vault_name, "-")
    error_message = "vault_name must be 3-24 alphanumeric/hyphen characters with no trailing hyphen."
  }
}

variable "sku_name" {
  type        = string
  description = "Key Vault SKU. Factory stores four short connection/credential strings; standard is sufficient and cheaper than premium."
  default     = "standard"
}

variable "purge_protection_enabled" {
  type        = bool
  description = "Purge protection. True in every environment: a vault is where the API key and connection strings live, and an unprotected vault that can be purged and immediately recreated is a recovery path an attacker would want. It does make the vault undeletable, which is why provider features keep recover_soft_deleted_key_vaults = true."
  default     = true
}

variable "soft_delete_retention_days" {
  type        = number
  description = "Days a soft-deleted vault is retained. Bicep parity used 90."
  default     = 90
}

variable "public_network_access_enabled" {
  type        = bool
  description = "Whether the vault accepts public traffic. The root wires this to the private-endpoint switch, so prod is closed by construction rather than by convention."
  default     = true
}

variable "create_private_endpoint" {
  type        = bool
  description = "Whether to create a vault private endpoint. The root drives this and public_network_access_enabled from one switch so they cannot disagree."
  default     = false
}

variable "private_endpoint_subnet_id" {
  type        = string
  description = "Subnet id for the private endpoint. Required when create_private_endpoint is true."
  default     = null
}

variable "private_dns_zone_id" {
  type        = string
  description = "Id of the privatelink.vaultcore.azure.net zone. Required when create_private_endpoint is true."
  default     = null
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to the vault."
  default     = {}
}
