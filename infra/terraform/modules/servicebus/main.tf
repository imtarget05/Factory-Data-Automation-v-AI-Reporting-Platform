# DELIVERY SEMANTICS — READ THIS BEFORE CHANGING ANYTHING HERE
#
# Service Bus Standard is AT-LEAST-ONCE. A message can be delivered more than
# once, and can arrive out of order relative to another message. This module
# therefore configures the broker to *help* deduplicate; it does not and cannot
# guarantee exactly-once processing.
#
# The broker-side controls are:
#   * duplicate detection on a 10-minute window (drops an exact re-send of the
#     same MessageId inside that window)
#   * a bounded max delivery count (poison message -> dead-letter, not an
#     infinite redelivery loop)
#   * a lock duration long enough for one stage, and a TTL long enough for a
#     backlog to be drained
#
# The SEMANTIC duplicate guard is `app/etl/servicebus_consumer.py` plus the
# `(run_id, stage)` uniqueness constraint in PostgreSQL. Broker duplicate
# detection is an optimisation; the constraint is the guarantee. Anything that
# claims otherwise is overclaiming.
#
# Queue + dead-letter are created together on purpose: a queue with no DLQ
# silently drops poison messages after maxDeliveryCount, which loses evidence
# exactly when the pipeline is already failing.

resource "azurerm_servicebus_namespace" "this" {
  name                = var.namespace_name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku_name

  minimum_tls_version           = var.minimum_tls_version
  public_network_access_enabled = var.public_network_access_enabled

  tags = var.tags
}

resource "azurerm_servicebus_queue" "telemetry" {
  name         = var.queue_name
  namespace_id = azurerm_servicebus_namespace.this.id

  requires_duplicate_detection            = true
  duplicate_detection_history_time_window = var.duplicate_detection_window
  dead_lettering_on_message_expiration    = true
  max_delivery_count                      = var.max_delivery_count
  default_message_ttl                     = var.message_ttl
  lock_duration                           = var.lock_duration
}

# Explicit DLQ. The broker creates one implicitly, but declaring it means its
# settings are reviewable here rather than inferred, and it makes the
# max_delivery_count on the DLQ a deliberate choice.
resource "azurerm_servicebus_queue" "telemetry_dead_letter" {
  name         = "${var.queue_name}-deadletter"
  namespace_id = azurerm_servicebus_namespace.this.id

  requires_duplicate_detection         = false
  dead_lettering_on_message_expiration = true
  max_delivery_count                   = var.max_delivery_count
  default_message_ttl                  = var.message_ttl
  lock_duration                        = var.lock_duration
}

# Private endpoint for the Service Bus data plane. Lives here so it cannot
# outlive the namespace.
resource "azurerm_private_endpoint" "servicebus" {
  count = var.create_private_endpoint ? 1 : 0

  name                = "pe-${var.namespace_name}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-servicebus"
    private_connection_resource_id = azurerm_servicebus_namespace.this.id
    subresource_names              = ["serviceBus"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dns-zone-group"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }

  tags = var.tags
}
