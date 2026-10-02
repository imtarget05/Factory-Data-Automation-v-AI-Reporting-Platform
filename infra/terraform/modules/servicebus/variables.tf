variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group holding the Service Bus namespace."
}

variable "namespace_name" {
  type        = string
  description = "Service Bus namespace name. 6-50 characters, letters/digits/hyphens, globally unique."
}

variable "queue_name" {
  type        = string
  description = "Telemetry ingestion queue name. ADR-0002 fixes this as factory-telemetry-inbox."
  default     = "factory-telemetry-inbox"
}

variable "sku_name" {
  type        = string
  description = "Namespace SKU. Standard is required for duplicate detection; Basic does not support it."
  default     = "Standard"
}

variable "minimum_tls_version" {
  type        = string
  description = "Minimum TLS. 1.2 matches Bicep parity and is the floor Azure accepts."
  default     = "1.2"
}

variable "public_network_access_enabled" {
  type        = bool
  description = "Whether the namespace accepts public traffic. Closed by construction in prod via the root's private-endpoint switch."
  default     = true
}

variable "duplicate_detection_window" {
  type        = string
  description = "Duplicate-detection window as an ISO-8601 duration. ADR-0002 specifies 10 minutes: long enough to absorb an Event Grid re-delivery burst, short enough that a genuine re-send of the same reading is not silently swallowed."
  default     = "PT10M"
}

variable "max_delivery_count" {
  type        = number
  description = "Deliveries before a message is dead-lettered. 10 is Bicep parity. The ETL stages that can legitimately fail are contract validation and transform, not network, so a high count is safe; a low one would dead-letter healthy messages during a transient outage."
  default     = 10
}

variable "lock_duration" {
  type        = string
  description = "Message lock duration. One stage of the pipeline holds a message; PT1M matches Bicep parity."
  default     = "PT1M"
}

variable "message_ttl" {
  type        = string
  description = "Default message time-to-live. 14 days (Bicep parity) is long enough for a queue backlog to be worked through after an incident."
  default     = "P14D"
}

variable "create_private_endpoint" {
  type        = bool
  description = "Whether to create a Service Bus private endpoint. The root drives this and public_network_access_enabled from one switch."
  default     = false
}

variable "private_endpoint_subnet_id" {
  type        = string
  description = "Subnet id for the private endpoint. Required when create_private_endpoint is true."
  default     = null
}

variable "private_dns_zone_id" {
  type        = string
  description = "Id of the privatelink.servicebus.windows.net zone. Required when create_private_endpoint is true."
  default     = null
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to the namespace."
  default     = {}
}
