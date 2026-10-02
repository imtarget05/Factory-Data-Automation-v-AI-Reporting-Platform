#!/usr/bin/env bash
# IaC validation for Factory-Data-Automation — RE-ANCHORED FROM BICEP.
#
# The Bicep stack is deleted. infra/terraform/ is the only infrastructure source
# of truth. This script used to compile every .bicep, resolve every
# .bicepparam, and assert security invariants on the compiled ARM output; with
# the templates gone those loops would find nothing and report success for
# having verified nothing.
#
# WHAT THIS SCRIPT DOES NOT DO: it never authenticates to Azure and never
# creates, updates or deletes a resource. `init` runs with `-backend=false`, so
# no remote state is contacted, and there is no `plan` or `apply` below. A green
# run means "the configuration is well-formed and the controls hold", NOT "the
# stack exists".
#
# FAIL-CLOSED, NOT VACUOUS: step 0 refuses to run when there is no Terraform, so
# this gate cannot report PASS by having nothing to check.
#
# Usage: infra/validate.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/terraform"

RED=$'\033[31m'
GREEN=$'\033[32m'
BOLD=$'\033[1m'
OFF=$'\033[0m'

failures=0
pass() { printf '%s  PASS%s  %s\n' "$GREEN" "$OFF" "$1"; }
fail() {
  printf '%s  FAIL%s  %s\n' "$RED" "$OFF" "$1"
  if [[ -n "${2:-}" ]]; then printf '        %s\n' "$2"; fi
  failures=$((failures + 1))
}

printf '%s-- 0. terraform present (never vacuous)%s\n' "$BOLD" "$OFF"
if ! command -v terraform >/dev/null 2>&1; then
  fail "terraform CLI" "not found on PATH; refusing to report PASS having checked nothing"
  exit 1
fi
if [[ ! -d "$TF_DIR" ]]; then
  fail "terraform sources" "infra/terraform does not exist — the gate would be vacuous"
  exit 1
fi
# `|| true`: find on an unreadable path exits 1, and under `set -e -o pipefail`
# that aborts the script BEFORE fail() can print. A gate that dies silently
# teaches people to re-run it.
tf_count="$(find "$TF_DIR" -name '*.tf' -not -path '*/.terraform/*' 2>/dev/null | wc -l | tr -d ' ' || true)"
if [[ "${tf_count:-0}" -eq 0 ]]; then
  fail "terraform sources" "no *.tf under infra/terraform — the gate would be vacuous"
  exit 1
fi
pass "terraform sources  ${tf_count} *.tf under infra/terraform"

cd "$TF_DIR"

printf '%s-- 1. terraform fmt%s\n' "$BOLD" "$OFF"
if out="$(terraform fmt -check -recursive 2>&1)"; then
  pass "fmt  clean"
else
  fail "fmt" "$out"
fi

printf '%s-- 2. init (backend disabled — no remote state is contacted)%s\n' "$BOLD" "$OFF"
if terraform init -backend=false -input=false >/dev/null 2>&1; then
  pass "init  providers resolved offline"
else
  fail "init" "terraform init -backend=false failed"
fi

printf '%s-- 3. terraform validate%s\n' "$BOLD" "$OFF"
if out="$(terraform validate 2>&1)"; then
  pass "validate  root configuration is valid"
else
  fail "validate" "$out"
fi

# WHY THERE IS NO PER-MODULE `init`/`validate` LOOP HERE. `terraform validate` at
# the root already validates every child module it references — proven by
# injecting a bogus argument into modules/network/main.tf, which made the root
# validate fail. A separate standalone `terraform init` inside each module is not
# just redundant, it is ACTIVELY WRONG: these modules carry no provider pin of
# their own, so a standalone init resolves the LATEST azurerm (v4) instead of the
# root's `~> 3.116` (v3), and reports v3-era argument names such as
# `enable_rbac_authorization` and `service_bus_queue_endpoint_id` as invalid.
# Three modules failed that way while the configuration they actually ship under
# is correct. Validating a module outside the version its caller pins manufactures
# failures that send people to "fix" working code.
#
# What root validate does NOT catch is an ORPHANED module: a directory under
# modules/ that nothing references. That is checked explicitly below.
wired="$(grep -oE 'source[[:space:]]*=[[:space:]]*"\./modules/[^"]+"' main.tf \
  | sed -E 's#.*\./modules/([^"]+)".*#\1#' | sort -u || true)"
on_disk="$(find modules -maxdepth 1 -mindepth 1 -type d -exec basename {} \; 2>/dev/null | sort)"
orphans="$(comm -13 <(printf '%s\n' "$wired") <(printf '%s\n' "$on_disk") | grep -v '^$' || true)"
missing="$(comm -23 <(printf '%s\n' "$wired") <(printf '%s\n' "$on_disk") | grep -v '^$' || true)"
if [[ -n "$orphans" ]]; then
  fail "orphaned modules" "on disk but not referenced by main.tf, so root validate never checks them: $orphans"
else
  pass "module wiring  $(printf '%s\n' "$wired" | grep -c .) module(s), all referenced by main.tf"
fi
if [[ -n "$missing" ]]; then
  fail "missing modules" "referenced by main.tf but absent on disk: $missing"
else
  pass "module presence  no dangling module references"
fi
printf '%s-- 4. plan-invariant checker self-tests must BITE%s\n' "$BOLD" "$OFF"
# A checker that has never been shown to fail is an assumption, not a control.
# These tests mutate plan fixtures and feed the checker unreadable, malformed and
# non-object JSON, requiring a fail-closed verdict and never a traceback.
if out="$(python3 -m pytest tests/test_check_plan_invariants.py -q 2>&1)"; then
  pass "plan-invariant self-tests  $(printf '%s' "$out" | grep -oE '[0-9]+ passed' | tail -1)"
else
  fail "plan-invariant self-tests" "$out"
fi

printf '%s-- 5. no secret values or real tenant ids in terraform%s\n' "$BOLD" "$OFF"
# Deliberately narrow: a broad /secret/ pattern matches the many legitimate
# references to secret NAMES and to the Key Vault module. Case-insensitive on
# purpose — the uppercase convention this repo uses is exactly what a
# case-sensitive grep misses.
leaked="$(grep -rniE "(password|clientSecret|accountKey|connectionString|sharedAccessKey)[[:space:]]*[:=][[:space:]]*['\"][^'\"]" \
  --include='*.tf' --include='*.tfvars' --exclude-dir=.terraform . \
  | grep -viE 'PLACEHOLDER|never committed' || true)"
if [[ -n "$leaked" ]]; then
  fail "secret scan" "$leaked"
else
  pass "secret scan  no literal secret values"
fi

# WHY THE PLACEHOLDER EXCEPTION IS NARROW AND NOT AN ALLOWLIST. The env tfvars
# may ship a password-shaped value so the configuration SHAPE (including the
# plan-time leak control) can be exercised with no real credential. A scanner
# that flags its own placeholders is a scanner people disable, and a disabled
# secret scan catches nothing at all. The exception requires the literal token
# PLACEHOLDER inside the value, and a real credential would have to contain that
# word to slip through.
placeholder_check="$(grep -rnE "^[[:space:]]*[a-z_]*(password|secret|key)[a-z_]*[[:space:]]*=" \
  --include='*.tfvars' --exclude-dir=.terraform . \
  | grep -viE 'PLACEHOLDER' | grep -E '=.*["'"'"'][^"'"'"']+["'"'"']' || true)"
if [[ -n "$placeholder_check" ]]; then
  fail "placeholder discipline" "these credential-shaped values carry no PLACEHOLDER marker: $placeholder_check"
else
  pass "placeholder discipline  every credential-shaped tfvars value is marked PLACEHOLDER"
fi

real_ids="$(grep -rniE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' \
  --include='*.tfvars' --exclude-dir=.terraform . \
  | grep -viE '0000000-0000-0000-0000-000000000000' || true)"
if [[ -n "$real_ids" ]]; then
  fail "environment identifiers" "$real_ids"
else
  pass "environment identifiers  placeholders only"
fi

printf '%s-- summary%s\n' "$BOLD" "$OFF"
if [[ "$failures" -eq 0 ]]; then
  printf '%s== IaC validation: ALL CHECKS PASSED ==%s (terraform — no Azure mutation)\n' "$GREEN" "$OFF"
  exit 0
fi
printf '%s== IaC validation: %d CHECK(S) FAILED ==%s\n' "$RED" "$failures" "$OFF"
exit 1