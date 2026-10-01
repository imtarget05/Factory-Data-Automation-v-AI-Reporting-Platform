# INTENTIONALLY EMPTY.
#
# Remote Terraform state is Phase 2 (ROADMAP "Terraform State + GitHub OIDC").
# It requires a repo-owned remote backend and a lock. Until that store exists,
# an empty `terraform {}` backend block would silently fall back to local state
# files, and a local state file is not durable state. The absence of a backend
# block is therefore the fail-closed choice, not an oversight.
#
# The check in tests/check_plan_invariants.py asserts this file stays empty
# until the Phase 2 backend is committed.
