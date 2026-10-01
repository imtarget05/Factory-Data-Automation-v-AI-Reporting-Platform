resource "azurerm_key_vault" "this" {
  name                = var.vault_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tenant_id           = var.tenant_id
  sku_name            = var.sku_name

  enable_rbac_authorization     = true
  soft_delete_retention_days    = var.soft_delete_retention_days
  purge_protection_enabled      = var.purge_protection_enabled
  public_network_access_enabled = var.public_network_access_enabled

  # NO SECRET VALUES ARE EVER DECLARED IN THIS MODULE.
  #
  # The vault is created empty. Values are written out of band (operator, or a
  # later pipeline step with a data-plane credential) and Terraform tracks
  # presence, not content. Two reasons this matters:
  #   1. A secret in HCL is a secret in git, in `.terraform/` and in the plan
  #      JSON. The plan JSON is an artefact the checker reads.
  #   2. `terraform destroy` / re-apply would otherwise need the value, which
  #      turns a routine rotation into a code change.
  #
  # The container app binds these NAMES as env vars. The name IS the binding
  # (see docs/enterprise-target/TERRAFORM-CONFIG-CONTRACT.md).

  network_acls {
    bypass         = "AzureServices"
    default_action = var.public_network_access_enabled ? "Allow" : "Deny"
  }

  tags = var.tags
}

# Private endpoint for the Key Vault data plane. Lives here rather than in the
# network module so it cannot outlive the vault.
resource "azurerm_private_endpoint" "vault" {
  count = var.create_private_endpoint ? 1 : 0

  name                = "pe-${var.vault_name}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-vault"
    private_connection_resource_id = azurerm_key_vault.this.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dns-zone-group-vault"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }

  tags = var.tags
}

