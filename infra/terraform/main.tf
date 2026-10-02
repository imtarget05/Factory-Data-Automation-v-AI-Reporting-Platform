resource "azurerm_resource_group" "this" {
  name     = local.names.resource_group
  location = var.location
  tags     = local.tags
}

module "network" {
  source = "./modules/network"

  location                 = var.location
  name_prefix              = var.name_prefix
  resource_group_name      = azurerm_resource_group.this.name
  deploy_private_endpoints = local.private_endpoints_enabled
  tags                     = local.tags
}

# ── observability ───────────────────────────────────────────────────────────
# First, because the Container Apps environment needs the Log Analytics
# workspace id, and because an app with no telemetry cannot be diagnosed when
# it breaks.
module "observability" {
  source = "./modules/observability"

  location                  = var.location
  resource_group_name       = azurerm_resource_group.this.name
  log_analytics_name        = local.names.law
  application_insights_name = local.names.app_insights
  retention_days            = var.log_analytics_retention_days
  action_group_name         = local.names.action_group
  alert_email               = var.alert_email
  alert_rules               = local.alert_rules
  tags                      = local.tags
}

# ── storage ─────────────────────────────────────────────────────────────────
module "storage" {
  source = "./modules/storage"

  location              = var.location
  account_name          = local.names.storage
  resource_group_name   = azurerm_resource_group.this.name
  replication_type      = local.storage_replication
  blob_soft_delete_days = 14
  zone_names            = var.blob_zone_names

  # ONE switch drives both, so public access and the private endpoint can never
  # disagree. Public access off with no private endpoint is unreachable; a
  # private endpoint with public access on is neither private nor useful.
  public_network_access_enabled = !local.private_endpoints_enabled
  create_private_endpoint       = local.private_endpoints_enabled
  private_endpoint_subnet_id    = local.private_endpoint_subnet_id
  private_dns_zone_id           = local.private_dns_zone_id.blob

  tags = local.tags
}

# ── identity ────────────────────────────────────────────────────────────────
module "identity" {
  source = "./modules/identity"

  location             = var.location
  resource_group_name  = azurerm_resource_group.this.name
  api_identity_name    = local.names.uami_api
  worker_identity_name = local.names.uami_worker
  tags                 = local.tags
}

# ── key vault ───────────────────────────────────────────────────────────────
module "keyvault" {
  source = "./modules/keyvault"

  location                 = var.location
  resource_group_name      = azurerm_resource_group.this.name
  vault_name               = local.names.key_vault
  tenant_id                = var.tenant_id
  purge_protection_enabled = true

  public_network_access_enabled = !local.private_endpoints_enabled
  create_private_endpoint       = local.private_endpoints_enabled
  private_endpoint_subnet_id    = local.private_endpoint_subnet_id
  private_dns_zone_id           = local.private_dns_zone_id.vaultcore

  tags = local.tags
}

# ── postgres ────────────────────────────────────────────────────────────────
module "postgres" {
  source = "./modules/postgres"

  location                  = var.location
  resource_group_name       = azurerm_resource_group.this.name
  server_name               = local.names.postgres
  administrator_login       = var.postgres_administrator_login
  administrator_password    = var.postgres_administrator_password
  sku_name                  = local.postgres_sku_name
  enable_private_endpoint   = local.private_endpoints_enabled
  delegated_subnet_id       = local.postgres_delegated_subnet_id
  private_dns_zone_id       = local.private_dns_zone_id.postgres
  high_availability_enabled = local.is_prod

  tags = local.tags
}

# ── service bus ─────────────────────────────────────────────────────────────
module "servicebus" {
  source = "./modules/servicebus"

  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  namespace_name      = local.names.service_bus
  queue_name          = "factory-telemetry-inbox"

  public_network_access_enabled = !local.private_endpoints_enabled
  create_private_endpoint       = local.private_endpoints_enabled
  private_endpoint_subnet_id    = local.private_endpoint_subnet_id
  private_dns_zone_id           = local.private_dns_zone_id.servicebus

  tags = local.tags
}

# ── event grid ──────────────────────────────────────────────────────────────
# After storage and service bus: the subscription references both by id.
module "eventgrid" {
  source = "./modules/eventgrid"

  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  topic_name                    = local.names.event_grid
  source_resource_id            = module.storage.account_id
  destination_queue_id          = module.servicebus.queue_id
  delivery_identity_resource_id = module.identity.worker_identity_id

  tags = local.tags
}

# ── container apps ──────────────────────────────────────────────────────────
# The API app. The ETL worker app is added in WAVE 2 once a worker entry point
# exists in `app/`; declaring it now would create a container that crash-loops
# on a missing command, which is worse than not deploying it.
module "container_app" {
  source = "./modules/container-app"

  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  environment_name    = local.names.container_env
  delegated_subnet_id = module.network.container_apps_subnet_id
  log_analytics_id    = module.observability.log_analytics_id
  internal_ingress    = false

  app_name           = local.names.api_app
  environment_id     = module.container_app.environment_id
  container_name     = "factory-api"
  image              = var.container_image
  identity_client_id = module.identity.api_client_id
  vault_uri          = module.keyvault.vault_uri
  secret_names       = var.api_secret_names
  min_replicas       = var.min_replicas
  max_replicas       = var.max_replicas

  # The revision suffix carries the source SHA, so the live revision name is
  # traceable to the commit that produced it.
  revision_suffix = substr(var.source_sha, 0, 8)

  extra_env = local.api_env

  tags     = local.tags
  app_tags = local.tags
}

# ── edge ────────────────────────────────────────────────────────────────────
# Instantiated only when enable_edge is true. A count of 0 means the plan
# contains zero edge resources, which is honest; a disabled-but-declared module
# would show resources that will never exist.
module "edge" {
  source = "./modules/edge"
  count  = var.enable_edge ? 1 : 0

  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  origin_hostname     = module.container_app.app_fqdn
  tags                = local.tags
}
