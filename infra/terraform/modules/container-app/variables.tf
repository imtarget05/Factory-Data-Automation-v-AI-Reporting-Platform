variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group holding the container apps."
}

variable "environment_name" {
  type        = string
  description = "Container Apps managed environment name. The environment is per-region and per-VNet, so prod and dev cannot share one."
}

variable "delegated_subnet_id" {
  type        = string
  description = "ACA infrastructure subnet id. Required; a managed environment cannot be created on an undelegated subnet."
}

variable "log_analytics_id" {
  type        = string
  description = "Log Analytics workspace id the environment streams container logs to."
}

variable "internal_ingress" {
  type        = bool
  description = "Whether the environment restricts ingress to the VNet. Requires a private load balancer in front; Phase 8 owns that path. Left false until the edge exists, because an internal environment with no LB is unreachable."
  default     = false
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to the environment."
  default     = {}
}

# ── The app itself ──────────────────────────────────────────────────────────
# The managed environment and the container app are separate concerns and
# separate files below, because the environment is expensive and long-lived
# while the app is redeployed on every image change.

variable "app_name" {
  type        = string
  description = "Container app name. The live app is ca-factory-api; a per-environment suffix keeps dev and prod on separate apps, which is required because one app cannot safely carry two different images or two different secrets."
}

variable "environment_id" {
  type        = string
  description = "Container Apps managed environment id. Passed in rather than created here so the app file depends on the environment's id, not on the environment module's internals."
}

variable "image" {
  type        = string
  description = "Immutable, digest-pinned OCI image. A tag is rejected: a mutable reference means the running code is not the code that was reviewed."

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be digest-pinned (repo@sha256:<64 hex>). Tags, including 'latest', are rejected."
  }
}


variable "identity_client_id" {
  type        = string
  description = "Client id of the same identity, required by the Container Apps resource."
}

variable "secret_names" {
  type        = list(string)
  description = "Key Vault secret NAMES bound as env vars. The vault is created empty and values are written out of band; Terraform tracks the reference, never the value. The name IS the env var name the application reads, so there is no second mapping to drift."

  validation {
    condition     = length(var.secret_names) > 0
    error_message = "secret_names must not be empty; the API reads FACTORY_API_KEY and a silent empty list would deploy the app in unauthenticated open mode (app/api/security.py)."
  }
}

variable "vault_uri" {
  type        = string
  description = "Key Vault URI (a public hostname, not a credential). The secret reference url is built from it, so the app does not need a second hand-maintained secret path."
}

variable "target_port" {
  type        = number
  description = "Container port. 8000 matches the live app and the uvicorn command in the image."
  default     = 8000
}

variable "external_ingress" {
  type        = bool
  description = "Whether ingress is internet-facing. The edge tier (Phase 8) is what makes an internal environment reachable; until that exists, external must stay true or the app has no ingress at all."
  default     = true
}

variable "allow_insecure" {
  type        = bool
  description = "Whether plain HTTP is accepted. Kept false in this repo: TLS terminates at the edge, and an allowInsecure app is a directly reachable HTTP endpoint."
  default     = false
}

variable "min_replicas" {
  type        = number
  description = "Minimum replicas. The live app is 1/1; multi-replica correctness is Phase 6."
  default     = 1
}

variable "max_replicas" {
  type        = number
  description = "Maximum replicas."
  default     = 3

  validation {
    condition     = var.max_replicas >= var.min_replicas
    error_message = "max_replicas must be >= min_replicas."
  }
}

variable "cpu" {
  type        = number
  description = "vCPU per replica. 0.5 matches the live app."
  default     = 0.5
}

variable "memory" {
  type        = string
  description = "Memory per replica. 1Gi matches the live app."
  default     = "1Gi"
}

variable "extra_env" {
  type        = map(string)
  description = "Non-secret environment variables, e.g. APPLICATIONINSIGHTS_CONNECTION_STRING, POSTGRES_HOST, LLM_PROVIDER. Secrets never appear here; they are bound by secretRef above."
  default     = {}
}

variable "workload_profile_name" {
  type        = string
  description = "Workload profile the app is scheduled on. The live environment is Consumption."
  default     = "Consumption"
}

variable "container_name" {
  type        = string
  description = "Container name inside the app. 'factory-api' for the API, 'factory-worker' for the ETL worker."
  default     = "factory-api"
}

variable "revision_suffix" {
  type        = string
  description = "Revision suffix appended to the generated revision name. Set to the source SHA (or a prefix of it) so the running revision can be traced to the commit that produced it, which is what makes 'which code is live' a lookup rather than a guess."
  default     = "rev"
}

variable "http_concurrent_requests" {
  type        = number
  description = "Concurrent requests per replica before the HTTP scale rule adds a replica. Inherited from Bicep parity (50); a starting point, not a measured value. Phase 7 replaces it with a number derived from the load test."
  default     = 50
}

variable "app_tags" {
  type        = map(string)
  description = "Tags applied to the container app (kept separate from the environment's tags so an app redeploy does not also retag the environment)."
  default     = {}
}
