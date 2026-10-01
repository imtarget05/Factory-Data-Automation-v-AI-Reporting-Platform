variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group holding the managed identities."
}

variable "api_identity_name" {
  type        = string
  description = "Name of the user-assigned identity the API container runs as. Read-only over gold and reports zones; granted nothing else."
  default     = "id-fac-api"
}

variable "worker_identity_name" {
  type        = string
  description = "Name of the user-assigned identity the ETL worker runs as. Writes the lake, drains the queue, owns the PostgreSQL server and is the Event Grid delivery identity."
  default     = "id-fac-worker"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to both identities."
  default     = {}
}
