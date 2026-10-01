output "resource_group_name" {
  description = "Name of the resource group this environment owns."
  value       = azurerm_resource_group.this.name
}

output "storage_account_name" {
  description = "Storage account name. Non-secret; the API reads it as configuration when public access is on."
  value       = module.storage.account_name
}

output "storage_blob_zones" {
  description = "Blob zone names actually created. The completion matrix compares this against the required five."
  value       = module.storage.zone_names
}

output "private_endpoints_enabled" {
  description = "Whether private endpoints and closed public access are in effect for this environment. Always true in prod."
  value       = local.private_endpoints_enabled
}

output "key_vault_name" {
  description = "Key Vault name. The vault is created EMPTY; values are written out of band."
  value       = module.keyvault.vault_name
}

output "postgres_server_fqdn" {
  description = "PostgreSQL host. Carries the host, not the credential."
  value       = module.postgres.server_fqdn
}

output "service_bus_queue_name" {
  description = "Telemetry ingestion queue name."
  value       = module.servicebus.queue_name
}

output "service_bus_dlq_name" {
  description = "Dead-letter queue name. The replay runbook references this."
  value       = "${module.servicebus.queue_name}-deadletter"
}

output "event_grid_topic_name" {
  description = "Event Grid topic carrying BlobCreated events."
  value       = local.names.event_grid
}

output "container_app_name" {
  description = "API container app name."
  value       = module.container_app.app_name
}

output "container_app_fqdn" {
  description = "API ingress hostname, or null when ingress is internal. Clients should reach the app through the edge hostname once the edge exists, not this one."
  value       = module.container_app.app_fqdn
}

output "api_identity_principal_id" {
  description = "Principal id of the API's managed identity. Needed for the data-plane role assignments (WAVE 2)."
  value       = module.identity.api_principal_id
}

output "worker_identity_principal_id" {
  description = "Principal id of the ETL worker's managed identity. Also the Event Grid delivery identity."
  value       = module.identity.worker_principal_id
}

output "edge_endpoint_hostname" {
  description = "Public edge hostname, or null when the edge tier is disabled."
  value       = var.enable_edge ? module.edge[0].endpoint_hostname : null
}

output "log_analytics_id" {
  description = "Log Analytics workspace id."
  value       = module.observability.log_analytics_id
}

output "alert_rule_ids" {
  description = "Created metric alert rule ids, keyed by the id used in locals.alert_rules."
  value       = module.observability.alert_rule_ids
}

output "source_sha_tag" {
  description = "The source SHA recorded as a tag on every resource. This is the value that ties a running resource back to a commit, and it is a tag only — it is NOT the OCI digest, NOT the revision name, and NOT a claim that the two match."
  value       = local.tags.source_sha
}