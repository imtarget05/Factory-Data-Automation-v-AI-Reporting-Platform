# validation — the environment CI is allowed to create and destroy.
#
# Purpose: prove the Terraform actually applies, without a long-lived bill and
# without touching prod. Per the ROADMAP execution contract, expensive resources
# may be transient: apply -> verify -> evidence -> destroy.
#
# This environment is the ONLY one CI may apply. dev is not provisioned by CI
# because a CI run that silently mutates a shared developer environment is a
# concurrency bug waiting to happen.
environment = "validation"
name_prefix = "facval"
location    = "eastasia"

# Deviates from prod: the data plane is public. Private endpoints add several
# minutes to apply and to destroy (each endpoint is a network resource with its
# own provisioning state), which makes the transient apply/destroy cycle slow
# and therefore more likely to be abandoned half-done. The PRIVATE PATH IS NOT
# PROVEN HERE — it is proven in prod, where it cannot be torn down. That gap is
# recorded rather than hidden.
enable_private_endpoints = false

# Deviates from prod: no edge. APIM and Front Door Premium are the two most
# expensive resources in this tree, and creating them on every CI run to prove
# they can be created is not a proportionate use of money. Edge is validated once
# manually in prod.
enable_edge = false

min_replicas = 1
max_replicas = 1

alert_email = null

blob_zone_names = [
  "raw-landing",
  "quarantine-corrupt",
  "silver-clean",
  "gold-marts",
  "reports",
]

# Not set: tenant_id, container_image, postgres_administrator_password. All three
# come from CI as TF_VAR_* / GitHub OIDC.
