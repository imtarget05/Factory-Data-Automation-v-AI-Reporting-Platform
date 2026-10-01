output "log_analytics_id" {
  description = "Resource id of the Log Analytics workspace. The Container Apps environment needs this to stream container logs."
  value       = azurerm_log_analytics_workspace.this.id
}

output "log_analytics_workspace_id" {
  description = "Workspace resource id. The Container Apps environment needs this id to stream container logs."
  value       = azurerm_log_analytics_workspace.this.id
}

output "application_insights_id" {
  description = "Resource id of the Application Insights component."
  value       = azurerm_application_insights.this.id
}

output "application_insights_connection_string" {
  description = "Connection string, written into the container as a non-secret configuration value (it is an ingestion endpoint, not a credential, and is required by the OTel exporter)."
  value       = azurerm_application_insights.this.connection_string
}

output "action_group_id" {
  description = "Id of the Monitor action group, or null when no action group was created."
  value       = try(azurerm_monitor_action_group.this[0].id, null)
}

output "alert_rule_ids" {
  description = "Ids of the created metric alert rules, keyed by the id used in the variable."
  value       = { for k, r in azurerm_monitor_metric_alert.this : k => r.id }
}