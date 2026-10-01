locals {
  # ONE deterministic name map. Nothing else in this tree concatenates a
  # resource name, so a naming change is a single-line change and every
  # resource name is greppable.
  names = {
    resource_group = "rg-${var.name_prefix}-${var.environment}"
    storage        = substr(replace("st${var.name_prefix}${var.environment}", "-", ""), 0, 24)
    key_vault      = "kv-${var.name_prefix}-${var.environment}"
    postgres       = "psql-${var.name_prefix}-${var.environment}"
    service_bus    = "sb-${var.name_prefix}-${var.environment}"
    event_grid     = "eg-${var.name_prefix}-${var.environment}"
    law            = "law-${var.name_prefix}-${var.environment}"
    app_insights   = "appi-${var.name_prefix}-${var.environment}"
    container_env  = "cae-${var.name_prefix}-${var.environment}"
    api_app        = "ca-${var.name_prefix}-api-${var.environment}"
    worker_app     = "ca-${var.name_prefix}-worker-${var.environment}"
    uami_api       = "id-${var.name_prefix}-api-${var.environment}"
    uami_worker    = "id-${var.name_prefix}-worker-${var.environment}"
    vnet           = "vnet-${var.name_prefix}-${var.environment}"
    action_group   = "ag-${var.name_prefix}-${var.environment}"
  }

  tags = {
    project     = "factory-data-automation"
    environment = var.environment
    managed_by  = "terraform"
    # The source SHA is injected by CI (TF_VAR_source_sha). Absent locally.
    source_sha = var.source_sha
  }

  is_prod = var.environment == "prod"

  # Private endpoints are mandatory in prod. This is a hard local, not a
  # convention: it is also asserted on the plan in
  # tests/check_plan_invariants.py so a caller cannot weaken it via tfvars.
  private_endpoints_enabled = var.enable_private_endpoints || local.is_prod

  # SKU deltas. Bicep parity used B1ms/Burstable for non-prod and D2ds_v5/
  # GeneralPurpose for prod.
  postgres_sku_name = local.is_prod ? "GP_Standard_D2ds_v5" : "B_Standard_B1ms"
  postgres_sku_tier = local.is_prod ? "GeneralPurpose" : "Burstable"

  storage_replication = local.is_prod ? "GRS" : "LRS"
  storage_tier        = local.is_prod ? "Standard" : "Standard"

  # The target zone model is five. A prod environment with a subset is a hard
  # failure, asserted in the plan checker rather than here, because the checker
  # is where a reader already looks for environment invariants.
  required_blob_zones = ["raw-landing", "quarantine-corrupt", "silver-clean", "gold-marts", "reports"]

  # Private-endpoint zone names, keyed by a short alias the modules use so the
  # full privatelink.* string appears exactly once in this repository.
  private_dns_zone_aliases = {
    blob       = "privatelink.blob.core.windows.net"
    postgres   = "privatelink.postgres.database.azure.com"
    servicebus = "privatelink.servicebus.windows.net"
    vaultcore  = "privatelink.vaultcore.azure.net"
  }

  # PostgreSQL needs its OWN delegated subnet, distinct from the private-endpoint
  # subnet. A server delegated to Microsoft.DBforPostgreSQL/flexibleServers and a
  # subnet hosting private endpoints cannot be the same subnet, and mixing them
  # fails at apply with a delegation conflict.
  postgres_delegated_subnet_name = "snet-psql"

  # Non-secret container configuration. Every value here is either a hostname, a
  # mode name, or a connection string for an INGREss endpoint. None of them is a
  # credential, and none may become one: a credential in this map would land in
  # the plan JSON that the invariant checker reads.
  api_env = merge(
    {
      PORT                          = "8000"
      ENVIRONMENT                   = var.environment
      AZURE_STORAGE_CONNECTION_MODE = "managed_identity"
      SERVICE_BUS_MODE              = "managed_identity"
      LLM_PROVIDER                  = "local"
      QUALITY_GATE_MODE             = "deterministic_fail_closed"
    },
    var.alert_email == null ? {} : {
      APPLICATIONINSIGHTS_CONNECTION_STRING = module.observability.application_insights_connection_string
    },
    local.private_endpoints_enabled ? {} : {
      STORAGE_ACCOUNT_NAME = module.storage.account_name
      KEY_VAULT_URI        = module.keyvault.vault_uri
      POSTGRES_HOST        = module.postgres.server_fqdn
      SERVICE_BUS_ENDPOINT = module.servicebus.service_bus_endpoint
    },
  )

  # Alert rules. Each one names the operational failure it is responsible for,
  # because an alert nobody can act on is a notification, not a control. The
  # servicebus_dlq_depth rule is the important one: a growing DLQ is the single
  # clearest signal that the pipeline is losing data quietly.
  alert_rules = {
    dlq_backlog = {
      display_name = "factory-dlq-backlog"
      description  = "Dead-letter queue is accumulating. Means messages are failing a stage repeatedly and evidence is being withheld from the pipeline. Runbook: docs/runbooks/dlq-replay.md"
      severity     = 2
      metric       = "ActiveMessages"
      threshold    = 1
      operator     = "GreaterThan"
      window       = "PT5M"
      frequency    = "PT1M"
    }
    data_stale = {
      display_name = "factory-data-stale"
      description  = "No successful ETL run inside the freshness budget. The pipeline is silent, not necessarily broken. Runbook: docs/runbooks/pipeline-stalled.md"
      severity     = 2
      metric       = "ActiveMessages"
      threshold    = 1
      operator     = "GreaterThan"
      window       = "PT15M"
      frequency    = "PT5M"
    }
    api_error_rate = {
      display_name = "factory-api-5xx"
      description  = "Server error ratio above 5%. Onset of an outage, or of a bad deploy. Runbook: docs/runbooks/api-5xx.md"
      severity     = 2
      metric       = "requests/failed"
      threshold    = 5
      operator     = "GreaterThan"
      window       = "PT5M"
      frequency    = "PT1M"
    }
    api_latency = {
      display_name = "factory-api-p95"
      description  = "95th percentile request latency above 2s. Precedes a timeout storm. Runbook: docs/runbooks/api-latency.md"
      severity     = 3
      metric       = "requests/duration"
      threshold    = 2000
      operator     = "GreaterThan"
      window       = "PT10M"
      frequency    = "PT5M"
    }
  }

  # Private DNS zone id by alias, or null when private endpoints are off. Every
  # caller goes through this function so a typo in a zone name is impossible
  # outside this file.
  private_dns_zone_id = {
    for alias, zone_name in local.private_dns_zone_aliases :
    alias => local.private_endpoints_enabled ? module.network.private_dns_zone_ids[zone_name] : null
  }

  # Private-endpoint subnet id, or null when private endpoints are off.
  private_endpoint_subnet_id = local.private_endpoints_enabled ? module.network.private_endpoint_subnet_id : null

  # PostgreSQL's own delegated subnet. See postgres_delegated_subnet_name above
  # for why it cannot share the private-endpoint subnet.
  postgres_delegated_subnet_id = local.private_endpoints_enabled ? module.network.postgres_subnet_id : null
}
