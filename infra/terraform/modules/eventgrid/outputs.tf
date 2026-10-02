output "topic_id" {
  description = "Resource id of the Event Grid topic."
  value       = azurerm_eventgrid_topic.this.id
}

output "subscription_id" {
  description = "Resource id of the BlobCreated-to-Service-Bus subscription."
  value       = azurerm_eventgrid_event_subscription.blob_to_servicebus.id
}
