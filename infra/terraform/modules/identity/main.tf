# USER-ASSIGNED MANAGED IDENTITIES (UAMI).
#
# WHY UAMI AND NOT SYSTEM-ASSIGNED
#
# The live Container App currently has `identity.type = None` and reaches
# everything through one static secret (`factory-api-key`). Two things force a
# change to identity rather than a secret rotation:
#
#   1. Multi-replica correctness. With a single shared API key there is no way
#      to tell one replica from another in an audit trail, and rotating the key
#      takes the whole fleet down at once.
#   2. Least privilege. The API needs read on gold/reports. The worker needs
#      write on raw/silver/gold plus queue-drain. A single secret cannot express
#      that split; two identities can.
#
# The identities are created here and GRANTED in a separate module, so the
# permission surface can be reviewed on its own. An identity with no role
# assignment is inert, which is the safe direction for a partial deploy.

resource "azurerm_user_assigned_identity" "api" {
  name                = var.api_identity_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = merge(var.tags, { role = "api-readonly" })
}

resource "azurerm_user_assigned_identity" "worker" {
  name                = var.worker_identity_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = merge(var.tags, { role = "etl-worker" })
}
