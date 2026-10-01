# EVENT GRID: BlobCreated (RAW) -> Service Bus telemetry queue
#
# This is the ingestion trigger. It is deliberately narrow:
#
#   * source filter is the RAW landing zone only. If the subscription covered
#     silver/gold, every pipeline write would produce another event and the
#     pipeline would trigger itself indefinitely.
#   * delivery is authenticated by the worker managed identity. There is no
#     access key and no connection string, because an event subscription
#     carrying a long-lived secret is a credential at rest in the resource
#     itself.
#   * the topic is a separate resource from storage and from Service Bus so a
#     blast radius in one does not take the others with it.

resource "azurerm_eventgrid_topic" "this" {
  name                = var.topic_name
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_eventgrid_event_subscription" "blob_to_servicebus" {
  name  = "blobcreated-to-telemetry"
  scope = var.source_resource_id

  event_delivery_schema = "EventGridSchema"

  included_event_types = var.source_event_types

  # Narrow the source to the raw and quarantine zones. A subscription on the
  # whole account would also fire on silver/gold/reports writes, and the
  # pipeline would then trigger itself in a loop.
  #
  # `advanced_filter` is used rather than `subject_filter` because this provider
  # version's `subject_filter` accepts exactly ONE `subject_begins_with` string
  # and there are two zones to include. The filter block takes a LIST, so both
  # zones are expressible without duplicating the subscription.
  advanced_filtering_on_arrays_enabled = true

  advanced_filter {
    string_begins_with {
      key    = "subject"
      values = ["/blobServices/default/containers/raw-landing", "/blobServices/default/containers/quarantine-corrupt"]
    }
  }

  # Authenticated by the worker managed identity. No access key, no connection
  # string: an event subscription carrying a long-lived secret is a credential
  # stored inside the resource, invisible to secret scanning.
  service_bus_queue_endpoint_id = var.destination_queue_id

  # Provider 3.x takes the identity TYPE plus the user-assigned identity RESOURCE
  # ID, not a principal id and client id pair.
  delivery_identity {
    type                   = "UserAssigned"
    user_assigned_identity = var.delivery_identity_resource_id
  }

  retry_policy {
    max_delivery_attempts = 30
    # 24h, not forever. An event that cannot be delivered for a day is not going
    # to become deliverable, and holding it forever converts a transient outage
    # into permanent backlog.
    event_time_to_live = 1440
  }
}
