output "namespace_id" {
  description = "Resource id of the namespace, used for role assignments and the private endpoint."
  value       = azurerm_servicebus_namespace.this.id
}

output "namespace_name" {
  description = "Name of the namespace."
  value       = azurerm_servicebus_namespace.this.name
}

output "service_bus_endpoint" {
  description = "Service Bus endpoint. Non-secret, passed to the container as configuration."
  value       = azurerm_servicebus_namespace.this.endpoint
}

output "queue_id" {
  description = "Resource id of the telemetry queue. The Event Grid subscription targets this."
  value       = azurerm_servicebus_queue.telemetry.id
}

output "queue_name" {
  description = "Name of the telemetry queue."
  value       = azurerm_servicebus_queue.telemetry.name
}

output "dead_letter_queue_id" {
  description = "Resource id of the dead-letter queue. The replay runbook references this by name."
  value       = azurerm_servicebus_queue.telemetry_dead_letter.id
}

output "identity_principal_id" {
  description = "System-assigned identity principal id of the namespace."
  value       = azurerm_servicebus_namespace.this.identity[0].principal_id
}

output "private_endpoint_id" {
  description = "Id of the Service Bus private endpoint, or null when private endpoints are disabled."
  value       = try(azurerm_private_endpoint.servicebus[0].id, null)
}
