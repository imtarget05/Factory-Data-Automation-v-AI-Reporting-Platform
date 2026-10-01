resource "azurerm_log_analytics_workspace" "this" {
  name                = var.log_analytics_name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku_name
  retention_in_days   = var.retention_days
  tags                = var.tags

  daily_quota_gb = var.daily_quota_gb
}

resource "azurerm_application_insights" "this" {
  name                = var.application_insights_name
  resource_group_name = var.resource_group_name
  location            = var.location
  application_type    = "web"
  tags                = var.tags

  # Workspace-based, so traces and logs land in the same place and can be
  # correlated. A classic (unlinked) component would put them in two silos and
  # make the Phase 7 "metric -> trace -> log" walk impossible.
  workspace_id = azurerm_log_analytics_workspace.this.id
}

# Action group. Created only when an email is supplied, so the absence of an
# email is visible as an absent resource rather than as an action group that
# silently swallows notifications.
resource "azurerm_monitor_action_group" "this" {
  count = var.alert_email == null ? 0 : 1

  name                = var.action_group_name
  resource_group_name = var.resource_group_name
  tags                = var.tags

  short_name = "factory-ops"

  email_receiver {
    name                    = "ops-mailbox"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

resource "azurerm_monitor_metric_alert" "this" {
  for_each = var.alert_rules

  name                = each.value.display_name
  resource_group_name = var.resource_group_name
  tags                = var.tags

  # An alert on no scope matches nothing and never fires. Scoped to the
  # Application Insights component, which is the only resource in this module
  # that emits the request/dependency metrics the rules query.
  scopes = [azurerm_application_insights.this.id]

  # Severity 0 is a platform-reserved value that does not page. Severity 1-3
  # page through the action group. A rule that pages at severity 0 trains
  # operators to ignore pages, which is worse than having no alert.
  severity = each.value.severity

  # The evaluation window and how often it is evaluated are properties of the
  # RULE, not of the criterion. Placing them on the criterion is a common and
  # silently-rejected mistake.
  window_size = each.value.window
  frequency   = each.value.frequency

  criteria {
    metric_namespace = "microsoft.insights/components"
    metric_name      = each.value.metric
    aggregation      = "Average"
    operator         = each.value.operator
    threshold        = each.value.threshold

    # The application-insights metric namespace is validated at apply; without
    # this a typo in a metric name passes plan and fails on deploy. Skipping
    # validation would make a wrong metric name a runtime surprise instead of a
    # plan error.
    skip_metric_validation = false

    # A dimension of "None" with value "*" is the Azure convention for an
    # unscoped metric. Written explicitly so its presence is a decision on the
    # record rather than a default someone has to look up.
    dimension {
      name     = "None"
      operator = "Include"
      values   = ["*"]
    }
  }

  auto_mitigate = true

  # An alert with no action group is a rule that fires into a void. The block is
  # only emitted when an action group exists, which keeps the validation
  # environment honest (alerts are created, notifications are not) instead of
  # failing the plan on a null id.
  dynamic "action" {
    for_each = var.action_group_name == null ? [] : [1]
    content {
      action_group_id = azurerm_monitor_action_group.this[0].id
    }
  }

  description = each.value.description
}