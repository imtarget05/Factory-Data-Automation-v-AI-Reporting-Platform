# dev — cheap, public data plane, no paging.
#
# Purpose: let a developer run the whole stack without a private network, and
# without an alert waking anybody. Every cost-saving choice here is a deliberate
# deviation from prod, and the deviations are listed rather than implied.
environment = "dev"
name_prefix = "facdev"
location    = "eastasia"

# Deviates from prod: public data plane. There is no VNet peering to protect,
# and building one for a scratch environment costs more than it secures.
enable_private_endpoints = false
enable_edge              = false

# Deviates from prod: no replicas beyond 1, no zone redundancy, no HA.
min_replicas = 1
max_replicas = 2

# No mailbox. The alert rules are still created so the config is exercised, but
# no action group exists, which means nothing pages anybody. Stated here rather
# than left as a null that a reader has to trace.
alert_email = null

# A subset of the zone model. raw/quarantine/silver/gold are the pipeline; the
# reports zone exists so an export can be written. A dev environment that creates
# all five costs one extra, nearly free, container — so this list is complete
# anyway, and only the PRODUCTION rule is a subset.
blob_zone_names = [
  "raw-landing",
  "quarantine-corrupt",
  "silver-clean",
  "gold-marts",
  "reports",
]

# NOT set here: tenant_id, container_image, postgres_administrator_password.
# Those are environment-specific and arrive as TF_VAR_* from the operator or CI.
# Committing a placeholder for any of them would turn a loud failure into a
# silent misconfiguration.
