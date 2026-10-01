resource "azurerm_postgresql_flexible_server" "this" {
  name                = var.server_name
  resource_group_name = var.resource_group_name
  location            = var.location
  version             = var.server_version
  sku_name            = var.sku_name
  storage_mb          = var.storage_mb
  administrator_login = var.administrator_login

  # Provider 3.x exposes public access and the private DNS zone as plain
  # attributes rather than blocks, so the mutual-exclusion rule below is
  # enforced by the module variable validation and again on the plan in
  # tests/check_plan_invariants.py, not by a `dynamic` block.
  public_network_access_enabled = !var.enable_private_endpoint
  private_dns_zone_id           = var.enable_private_endpoint ? var.private_dns_zone_id : null
  delegated_subnet_id           = var.enable_private_endpoint ? var.delegated_subnet_id : null

  high_availability {
    mode = var.high_availability_enabled ? "ZoneRedundant" : "Disabled"
  }

  backup_retention_days = 7

  # Entra-only administration is the target. A password is only accepted when
  # explicitly supplied, so the end state is the absence of a credential rather
  # than its rotation.
  administrator_password = var.administrator_password

  tags = var.tags
}

# Private endpoint for the PostgreSQL data plane. Lives here so it cannot
# outlive the server.
resource "azurerm_private_endpoint" "postgres" {
  count = var.enable_private_endpoint ? 1 : 0

  name                = "pe-${var.server_name}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-postgres"
    private_connection_resource_id = azurerm_postgresql_flexible_server.this.id
    subresource_names              = ["server"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dns-zone-group"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }

  tags = var.tags
}
