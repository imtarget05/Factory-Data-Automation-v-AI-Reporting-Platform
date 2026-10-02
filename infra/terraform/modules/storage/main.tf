resource "azurerm_storage_account" "this" {
  name                     = var.account_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = var.account_tier
  account_replication_type = var.replication_type

  # StorageV2 is required for the zone model (block blob + ADLS semantics).
  account_kind = "StorageV2"

  access_tier = "Hot"

  # ── Security properties asserted on the plan by
  # tests/check_plan_invariants.py. Changing any of these must fail the gate.
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = var.public_network_access_enabled

  # Shared-key access stays enabled for the parity window: the offline
  # adapter and the local ETL read Blob with a connection string. Phase 6
  # (managed identity) is what turns this off; the variable makes that a
  # one-line change rather than a rewrite.
  shared_access_key_enabled = true

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = var.blob_soft_delete_days
    }

    container_delete_retention_policy {
      days = var.blob_soft_delete_days
    }
  }

  network_rules {
    # `enabled = false` means "do not apply an IP allowlist". The public
    # network access flag above is the real gate; keeping these two separate
    # avoids the common bug where a permissive default quietly overrides it.
    bypass         = ["AzureServices"]
    default_action = var.public_network_access_enabled ? "Allow" : "Deny"
  }

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

resource "azurerm_storage_container" "zone" {
  for_each = toset(var.zone_names)

  name                  = each.value
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"

  metadata = {
    # Self-describing zones: an operator looking at the portal sees what the
    # container is for without reading code.
    managed_zone = each.value
  }
}

# Private endpoint for the blob data plane. It lives in the storage module, not
# the network module, so it cannot outlive the account it fronts.
resource "azurerm_private_endpoint" "blob" {
  count = var.create_private_endpoint ? 1 : 0

  name                = "pe-${var.account_name}-blob"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id
  private_service_connection {
    name                           = "psc-blob"
    private_connection_resource_id = azurerm_storage_account.this.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "dns-zone-group"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }
  tags = var.tags
}

