resource "azurerm_container_app_environment" "this" {
  name                = var.environment_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags

  # Provider 3.x exposes the Consumption-profile environment as flat
  # attributes rather than the nested `vnet_configuration` block that the
  # Workload-Profiles environment uses. The live Factory environment is
  # Consumption (`workloadProfileName: Consumption` on ca-factory-api), so the
  # flat form is the correct one here; moving to Workload Profiles in a later
  # phase means migrating these three attributes into `vnet_configuration`, and
  # the comment exists so that change is not mistaken for a fix.
  infrastructure_subnet_id       = var.delegated_subnet_id
  log_analytics_workspace_id     = var.log_analytics_id
  internal_load_balancer_enabled = var.internal_ingress
}

# ── The app ─────────────────────────────────────────────────────────────────
#
# SECRETS ARE REFERENCES, NOT VALUES.
#
# Each name in var.secret_names becomes a `secret` block whose `keyvault_ref`
# points at the vault, plus an env var of the SAME name bound to that secret.
# The Container Apps data-plane contract is that the app's identity reads the
# secret at start-up: the value never appears in the ARM payload, in the plan
# JSON, or in this repository. Because the env var name and the secret name are
# the same string, there is no second mapping that can drift — see
# docs/enterprise-target/TERRAFORM-CONFIG-CONTRACT.md.
resource "azurerm_container_app" "this" {
  name                         = var.app_name
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.environment_id
  workload_profile_name        = var.workload_profile_name
  tags                         = var.app_tags

  # Single-revision mode. The app is a stateless API, so there is no reason to
  # retain older revisions; "Multiple" keeps every previous image alive and
  # makes "which code is live" ambiguous.
  revision_mode = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_client_id]
  }

  # Provider 3.x takes the secret RESOURCE url, not a nested `keyvault_ref`
  # block. The url is built from the vault URI, which is a public hostname and
  # not a credential.
  dynamic "secret" {
    for_each = var.secret_names
    content {
      name                = secret.value
      identity            = var.identity_client_id
      key_vault_secret_id = "${trimsuffix(var.vault_uri, "/")}/secrets/${secret.value}"
    }
  }

  ingress {
    external_enabled           = var.external_ingress
    target_port                = var.target_port
    transport                  = "auto"
    allow_insecure_connections = var.allow_insecure

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    revision_suffix = var.revision_suffix

    container {
      name   = var.container_name
      image  = var.image
      cpu    = var.cpu
      memory = var.memory

      # Probes exist. The live app has `probes: []`, which is why a
      # scale-from-zero cold start is invisible to Azure — the earlier live
      # probe in the evidence log timed out at 15 s and again at 60 s with
      # nothing watching. A liveness and a readiness probe is the difference
      # between "the app is slow to start" and "the app is broken".
      liveness_probe {
        path                    = "/api/v1/health"
        port                    = var.target_port
        transport               = "auto"
        initial_delay           = 10
        interval_seconds        = 15
        timeout                 = 5
        failure_count_threshold = 3
      }

      # The readiness probe takes no `initial_delay` in this provider version:
      # the attribute exists on the liveness probe only. That is also the
      # correct behaviour — the point of a readiness probe is to withdraw the
      # replica from traffic the moment it is not serving, not to sit out a
      # start-up delay first.
      readiness_probe {
        path                    = "/api/v1/health"
        port                    = var.target_port
        transport               = "auto"
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 3
      }

      # Non-secret configuration first, then the secret bindings. Order is
      # not semantically meaningful, but grouping it this way makes a review of
      # "what does this container know" a single read.
      dynamic "env" {
        for_each = var.extra_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_names
        content {
          name        = env.value
          secret_name = env.value
        }
      }
    }

    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    # HTTP autoscaling. The threshold is inherited from Bicep parity (50
    # concurrent requests) and is a STARTING POINT, not a measured value;
    # Phase 7 replaces it with a number derived from the load test.
    http_scale_rule {
      name                = "factory-http"
      concurrent_requests = var.http_concurrent_requests
    }
  }
}
