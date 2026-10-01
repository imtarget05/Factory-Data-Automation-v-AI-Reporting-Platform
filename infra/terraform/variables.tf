variable "environment" {
  type        = string
  description = "Deployment environment. Drives SKU/retention/replica deltas."
  validation {
    condition     = contains(["dev", "validation", "prod"], var.environment)
    error_message = "environment must be one of: dev, validation, prod."
  }
}

variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

variable "name_prefix" {
  type        = string
  description = "Short, lowercase-alphanumeric name prefix. Azure resource names are globally unique for storage/keyvault, so this must be specific per environment."
  default     = "fac"
  validation {
    condition     = can(regex("^[a-z0-9]{3,10}$", var.name_prefix))
    error_message = "name_prefix must be 3-10 lowercase alphanumeric characters."
  }
}

variable "tenant_id" {
  type        = string
  description = "Microsoft Entra tenant id that owns the Key Vault and the PostgreSQL Entra administrator."
  # No default and no placeholder: a wrong value must fail loudly, not deploy.
}

variable "postgres_administrator_login" {
  type        = string
  description = "PostgreSQL Entra administrator login name (an Entra object, not a local user)."
  default     = "pgadmin"
}

variable "postgres_administrator_password" {
  type        = string
  description = "PostgreSQL administrator password. Supplied via TF_VAR_*, never committed. Phase 6 replaces the password with Entra-only auth; this variable exists for the parity window."
  sensitive   = true
  default     = null
}

variable "container_image" {
  type        = string
  description = "Fully-qualified immutable OCI image reference for the API container, digest-pinned. A tag-only reference is rejected by validation so a mutable 'latest' cannot reach production."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.container_image))
    error_message = "container_image must be digest-pinned, e.g. ghcr.io/org/repo@sha256:<64 hex>. Tags (including 'latest') are rejected."
  }
}

variable "api_secret_names" {
  type        = list(string)
  description = "Key Vault secret NAMES bound as Container App env vars. The name IS the environment variable name the application reads (see docs/enterprise-target/TERRAFORM-CONFIG-CONTRACT.md). Values are never passed through Terraform."
  default     = ["FACTORY_API_KEY"]
  validation {
    condition     = length(var.api_secret_names) > 0
    error_message = "api_secret_names must not be empty; the API has no non-secret configuration in this environment."
  }
  validation {
    condition     = alltrue([for n in var.api_secret_names : can(regex("^[A-Z][A-Z0-9_]*$", n))])
    error_message = "Each secret name must be UPPER_SNAKE_CASE, because it is used verbatim as the container env var name."
  }
}

variable "enable_private_endpoints" {
  type        = bool
  description = "When true, data-plane resources get private endpoints and public network access is disabled. dev/validation default to false to keep iteration cheap; prod must set true."
  default     = false
}

variable "min_replicas" {
  type        = number
  description = "Minimum replicas for the API container app."
  default     = 1
}

variable "max_replicas" {
  type        = number
  description = "Maximum replicas for the API container app."
  default     = 3
  validation {
    condition     = var.max_replicas >= var.min_replicas
    error_message = "max_replicas must be >= min_replicas."
  }
}

variable "log_analytics_retention_days" {
  type        = number
  description = "Log Analytics retention. Bicep parity used 30 days."
  default     = 30
}

variable "source_sha" {
  type        = string
  description = "Git source SHA this apply is building from, recorded as a tag. Injected by CI as TF_VAR_source_sha so the deployed resource carries the exact commit that produced it. Defaults to 'unknown' for local runs; the plan checker requires a real SHA when environment is prod."
  default     = "unknown"
}

variable "alert_email" {
  type        = string
  description = "Monitored mailbox that receives alert notifications. This is the only human route back from a page, so it must be a mailbox someone actually reads. Null in dev/validation: the alert rules are still created, but with no action group, which is honest about the fact that nothing is paging anyone."
  default     = null
}

variable "blob_zone_names" {
  type        = list(string)
  description = "Medallion zones. The five-zone model is the target; a shorter list is permitted only outside prod, and the prod environment file passes all five."
  default     = ["raw-landing", "quarantine-corrupt", "silver-clean", "gold-marts", "reports"]

  validation {
    condition     = alltrue([for z in var.blob_zone_names : can(regex("^[a-z0-9-]{3,63}$", z)) && !endswith(z, "-")])
    error_message = "Each blob zone name must be 3-63 lowercase alphanumeric/hyphen characters with no trailing hyphen."
  }
}

variable "enable_edge" {
  type        = bool
  description = "Provision the edge (Front Door Premium + WAF + APIM) tier. Off by default: the edge is real recurring cost and Phase 8 owns proving it is worth it. When off, the module is not instantiated at all rather than instantiated with no resources, so `terraform plan` shows zero edge resources instead of a disabled placeholder."
  default     = false
}
