# Terraform parity with infra/modules/network/vnet.bicep.
#
# Bicep baseline: one VNet, an ACA subnet and a second subnet, referenced by the
# Container Apps module. It had no private endpoints and no private DNS.
# Target (ROADMAP Phase 4): the same VNet plus private endpoints for every
# data-plane dependency (Postgres, Storage, Service Bus, Key Vault) and the
# matching private DNS zones.
#
# A private endpoint lives with the module that owns its target, not here. That
# is a deliberate split: a `network` module that also declared the storage
# private endpoint would create a dependency inversion (network would need the
# storage account id, storage would need the subnet id) and a private endpoint
# could then outlive the resource it fronts. This module owns the VNet, the
# subnets and the DNS zones; each data-plane module owns its own endpoint.

resource "azurerm_virtual_network" "this" {
  name                = "vnet-${var.name_prefix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  address_space       = var.address_space
  tags                = var.tags
}

resource "azurerm_subnet" "container_apps" {
  name                 = "snet-aca"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.aca_subnet_address_prefix]

  # Service delegation is required before a subnet may host a Container Apps
  # environment. It cannot be conditional: an environment created on an
  # undelegated subnet fails at apply time with an opaque error.
  #
  # Provider 3.x accepts the delegation service NAME only. The permitted action
  # set is implied by that name and is not writable through this block, so the
  # note exists to stop a future attempt to add an `actions` argument that the
  # provider will reject.
  delegation {
    name = "Microsoft.App/environments"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "private_endpoints" {
  name                 = "snet-pe"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.private_endpoint_subnet_address_prefix]

  # Private endpoints carry no delegation: delegation is a claim that a subnet
  # is dedicated to one service, and a private endpoint subnet serves many.
}

resource "azurerm_subnet" "postgres" {
  name                 = "snet-psql"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.postgres_subnet_address_prefix]

  # A PostgreSQL flexible server in private-access mode must sit on a subnet
  # delegated to it. It cannot share the private-endpoint subnet: that subnet
  # carries no delegation because a private endpoint subnet serves many targets.
  delegation {
    name = "Microsoft.DBforPostgreSQL/flexibleServers"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Private DNS zones. The list is static rather than derived from the enabled
# endpoints so that turning an endpoint on in a later apply also creates the
# zone, instead of failing on a missing zone.
resource "azurerm_private_dns_zone" "this" {
  for_each = var.deploy_private_endpoints ? toset(local.private_dns_zone_names) : toset([])

  name                = each.value
  resource_group_name = var.resource_group_name
  tags                = var.tags
}
