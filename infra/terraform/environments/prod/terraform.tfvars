# prod — the only environment that is meant to survive.
#
# NOTHING IN THIS FILE IS OPTIONAL. Every value here is the production posture,
# and the plan checker in tests/check_plan_invariants.py asserts the ones that
# can be weakened by a tfvars override. The values are written out rather than
# inherited so that a reader can see the production intent without tracing
# locals.
environment = "prod"
name_prefix = "facprod"
location    = "eastasia"

# Deviates from prod: nothing. Production is private, zone-redundant, has
# multiple replicas, and pages a real mailbox.
enable_private_endpoints = true
enable_edge              = true

min_replicas = 2
max_replicas = 10

# MUST be a monitored mailbox. Null here means an action group is not created and
# every alert rule fires into a void. The plan checker fails a prod plan whose
# alert_email is null, for exactly that reason.
alert_email = "binhtan5734@gmail.com"

# The full five-zone model. A prod plan with fewer than five is rejected by the
# plan checker.
blob_zone_names = [
  "raw-landing",
  "quarantine-corrupt",
  "silver-clean",
  "gold-marts",
  "reports",
]

# Not set here, and that is deliberate:
#   tenant_id                    — comes from the pipeline's OIDC context
#   container_image              — the digest-pinned image built from the commit
#                                 being deployed, injected as TF_VAR_container_image
#   postgres_administrator_password — should be null in the target state (Entra-only
#                                 admin). It is left unset so that the server is
#                                 created without a password credential, and the
#                                 absence is the point.
#
# source_sha is NOT set here either: CI injects the commit SHA, so the tag on
# every resource is the code that produced it rather than whatever the tfvars
# file last said.
