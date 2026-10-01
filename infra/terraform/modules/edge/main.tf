# WAF. Managed rules only. The custom-rule block exists and is empty, which is
# correct: an empty custom rule list is a reviewable "no custom rules yet",
# whereas omitting the block entirely hides whether custom rules were considered.
resource "azurerm_cdn_frontdoor_firewall_policy" "this" {
  # Letters and digits only, no hyphens. The Azure name rule for this resource
  # is stricter than for the other edge resources, and the hyphens that read
  # naturally in "fdp-factory" are rejected here.
  name                = "fdpFactory"
  resource_group_name = var.resource_group_name
  sku_name            = "Premium_AzureFrontDoor"
  enabled             = true
  mode                = var.waf_mode
  tags                = var.tags
}

# Front Door profile + endpoint. The profile is Premium because WAF on the edge
# is Premium-only; Standard would drop the WAF requirement silently.
resource "azurerm_cdn_frontdoor_profile" "this" {
  name                = "afd-factory"
  resource_group_name = var.resource_group_name
  sku_name            = "Premium_AzureFrontDoor"
  tags                = var.tags
}

# The endpoint is a child of the profile and inherits its resource group, so it
# takes no resource_group_name of its own.
resource "azurerm_cdn_frontdoor_endpoint" "this" {
  name                     = "afd-factory-endpoint"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.this.id
  enabled                  = true
}

# APIM. Consumption for validation: serverless, scales to zero, negligible at
# this traffic. The prod SKU is a Phase 8 decision against a measured baseline,
# not a guess written here.
resource "azurerm_api_management" "this" {
  name                = "apim-factory"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku_name            = "Consumption_0"

  # Required by the provider and shown in the developer portal. A real mailbox:
  # "admin@example.com" would ship a service whose vendor contact path is dead.
  publisher_name  = "Factory Data Automation Platform"
  publisher_email = var.publisher_email

  tags = var.tags
}

# The rate-limit policy is the reason APIM is in this tree at all. The numbers
# are placeholders until a traffic baseline exists; what is NOT a placeholder is
# that a policy exists, so the Phase 8 discussion is about values rather than
# about whether anyone thought of limiting.
resource "azurerm_api_management_api" "factory" {
  name                = "factory"
  resource_group_name = var.resource_group_name
  api_management_name = azurerm_api_management.this.name
  revision            = "v1"
  path                = "factory"
  protocols           = ["https"]

  display_name = "Factory Data Automation API"
  api_type     = "http"

  service_url = "https://${var.origin_hostname}"

  subscription_required = false
}

resource "azurerm_api_management_api_policy" "rate_limit" {
  api_name            = azurerm_api_management_api.factory.name
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name

  # API-level, not operation-level. The per-operation policy resource requires a
  # literal operation id and rejects the "*" wildcard, so a per-operation policy
  # would mean enumerating every operation and would silently stop limiting the
  # moment a new endpoint was added. At the API level the inbound base policy
  # runs for every operation, including ones added later.
  xml_content = <<POLICY
<policies>
  <inbound>
    <base />
    <rate-limit calls="${var.rate_limit_per_minute}" window-size="60" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
POLICY
}
