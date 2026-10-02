variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

# MEDALLION ZONE CONTRACT (Terraform parity with infra/modules/storage/blob.bicep)
#
# Bicep baseline: 4 containers — raw-landing, silver-clean, gold-marts,
# quarantine-corrupt.
# Target (ROADMAP "Blob zones" row + ADR-0002): 5 zones, adding `reports`
# because the exporter persists Excel/PDF artefacts (app/reports/exporter.py)
# and the report needs a durable, non-ephemeral home.
#
# The `reports` container is ADDED here. It is the one intentional
# parity-extension, and it is called out in
# docs/enterprise-target/TERRAFORM-PARITY-MATRIX.md so it is never mistaken
# for a faithful copy of Bicep.

variable "account_name" {
  type        = string
  description = "Storage account name. 3-24 lowercase alphanumeric characters, globally unique."

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.account_name))
    error_message = "account_name must be 3-24 lowercase alphanumeric characters."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Resource group that holds the storage account. Passed in rather than created here so ownership of the group is explicit and shared across modules."
}



variable "account_tier" {
  type        = string
  description = "Storage account performance tier. The lakehouse workload is analytics-flavored, but Hot/Premium costs; Standard_LRS in non-prod keeps iteration cheap and is what Bicep parity used."
  default     = "Standard"
}

variable "replication_type" {
  type        = string
  description = "Storage replication type. Non-prod uses LRS; prod uses GRS because a single-region loss of the raw landing zone would destroy the append-only source of truth."
  default     = "LRS"
  validation {
    condition     = contains(["LRS", "GRS", "RAGRS", "ZRS", "GZRS"], var.replication_type)
    error_message = "replication_type must be a valid azurerm storage replication type."
  }
}

variable "blob_soft_delete_days" {
  type        = number
  description = "Days a deleted blob is retained. Bicep parity used 14 for both blob and container delete retention. Quarantine depends on this: a mistaken delete of an evidence file must be recoverable."
  default     = 14
}

variable "zone_names" {
  type        = list(string)
  description = "Blob container names created under the default blob service. Order is irrelevant; uniqueness is enforced by Terraform. No implicit 'reports' is added: the caller states the full set so an absent zone is a visible diff, not a silent default."
  default     = ["raw-landing", "quarantine-corrupt", "silver-clean", "gold-marts", "reports"]

  validation {
    condition     = length(distinct(var.zone_names)) == length(var.zone_names)
    error_message = "zone_names must not contain duplicates."
  }

  validation {
    condition     = alltrue([for z in var.zone_names : can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", z))])
    error_message = "Each zone name must be 3-63 chars, lowercase alphanumeric/hyphen, and start and end alphanumeric."
  }
}

variable "public_network_access_enabled" {
  type        = bool
  description = "Whether the storage account accepts public data-plane traffic. True is required for the offline/local dev path; the root wires it to the private-endpoint switch so prod is closed by construction."
  default     = true
}

variable "create_private_endpoint" {
  type        = bool
  description = "Whether to create a blob private endpoint. The root sets this from the same switch that disables public network access, so the two can never disagree: enabling one without the other would produce an account that is neither reachable nor closed."
  default     = false
}

variable "private_endpoint_subnet_id" {
  type        = string
  description = "Subnet id for the private endpoint. Required when create_private_endpoint is true."
  default     = null
}

variable "private_dns_zone_id" {
  type        = string
  description = "Id of the privatelink.blob.core.windows.net zone. Required when create_private_endpoint is true."
  default     = null
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to every resource in this module."
  default     = {}
}
