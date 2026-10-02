output "api_identity_id" {
  description = "Resource id of the API's user-assigned identity."
  value       = azurerm_user_assigned_identity.api.id
}

output "api_principal_id" {
  description = "Principal (object) id of the API's identity. This is what a role assignment targets."
  value       = azurerm_user_assigned_identity.api.principal_id
}

output "api_client_id" {
  description = "Client id of the API's identity. Required wherever a resource must be read on the app's behalf."
  value       = azurerm_user_assigned_identity.api.client_id
}

output "worker_identity_id" {
  description = "Resource id of the ETL worker's user-assigned identity."
  value       = azurerm_user_assigned_identity.worker.id
}

output "worker_principal_id" {
  description = "Principal id of the worker's identity. Also the Event Grid delivery identity."
  value       = azurerm_user_assigned_identity.worker.principal_id
}

output "worker_client_id" {
  description = "Client id of the worker's identity."
  value       = azurerm_user_assigned_identity.worker.client_id
}
