variable "location" {
  type        = string
  description = "Azure region for every resource in this environment."
  default     = "eastasia"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group holding the Event Grid topic."
}

variable "topic_name" {
  type        = string
  description = "Event Grid topic name. Globally unique."
}

variable "destination_queue_id" {
  type        = string
  description = "Resource id of the Service Bus queue that receives the events."
}

variable "source_resource_id" {
  type        = string
  description = "Storage account id whose BlobCreated events are published. Passed in rather than referenced so this module does not depend on the storage module's internals."
}

variable "source_event_types" {
  type        = list(string)
  description = "Event types forwarded. Only BlobCreated: the pipeline is triggered by new raw files, not by silver/gold writes. Subscribing to those too would make the pipeline trigger itself in a loop."
  default     = ["Microsoft.Storage.BlobCreated"]

  validation {
    condition     = alltrue([for t in var.source_event_types : t == "Microsoft.Storage.BlobCreated"])
    error_message = "Only Microsoft.Storage.BlobCreated is permitted. Wiring silver/gold writes back into the trigger creates an ingestion loop."
  }
}

variable "delivery_identity_resource_id" {
  type        = string
  description = "RESOURCE id of the user-assigned identity Event Grid authenticates as when delivering to Service Bus. A resource id, not a principal id: the provider resolves the principal from it. No client secret, because a subscription carrying a long-lived secret is a credential stored inside the resource, invisible to secret scanning."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to the topic."
  default     = {}
}
