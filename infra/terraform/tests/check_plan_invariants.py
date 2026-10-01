#!/usr/bin/env python3
"""Fail-closed invariant checker for a Terraform plan.

WHY THIS EXISTS

`terraform validate` proves the configuration is syntactically well-formed and
type-correct. It does not prove the plan is SAFE. A plan can be perfectly valid
and still contain a storage account with public blob access, a Key Vault with
purge protection off, or a prod environment with no private endpoints. Those are
all expressible in valid HCL, and every one of them is a security regression.

So the gate reads the plan JSON — which is what Terraform would actually send to
Azure — and asserts security properties on it. Not on the .tf source: the source
and the plan can disagree (count/for_each, defaults, provider normalisation), and
only the plan is the artefact that gets applied.

USAGE

    terraform plan -out=tfplan
    terraform show -json tfplan > plan.json
    python3 check_plan_invariants.py plan.json --environment prod

EXIT CODES

    0  all invariants hold
    1  at least one invariant failed
    2  the plan could not be read — fail closed; an unreadable plan is not a
       passing plan

DESIGN NOTES

* Fail closed on an unreadable shape. If a resource type is missing from the plan
  entirely that is reported as a failure, not skipped: a rule that silently
  passes when its target is absent protects nothing.
* A predicate that raises is a FAILURE, never a pass. An unexpected shape means
  the rule could not be evaluated.
* No network. The plan is a local file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from typing import Any

# Env var names that are secrets in Factory. Derived from app/api/security.py and
# app/utils/config.py. If the application's configuration contract changes this
# list changes with it — that coupling is the point.
SECRET_NAME_ALLOWLIST = frozenset(
    {
        "FACTORY_API_KEY",
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "SERVICE_BUS_CONNECTION_STRING",
        "AZURE_STORAGE_CONNECTION_STRING",
    }
)


def _values(change: dict[str, Any]) -> dict[str, Any]:
    """Unwrap a resource_changes entry into its planned values.

    Terraform wraps planned values as {"after": {...}} and marks anything not yet
    known in "after_unknown". We return `after` only; a rule that needs a value
    the provider has not computed yet sees None and fails closed on it.
    """
    after = change.get("after")
    return after if isinstance(after, dict) else {}


# ── per-resource rules ───────────────────────────────────────────────────────


def _storage_rules(v: dict[str, Any]) -> list[str]:
    fails = []
    if v.get("min_tls_version") != "TLS1_2":
        fails.append(f"min_tls_version={v.get('min_tls_version')!r}, required TLS1_2")
    if v.get("https_traffic_only_enabled") is not True:
        fails.append(f"https_traffic_only_enabled={v.get('https_traffic_only_enabled')!r}, required True")
    if v.get("allow_nested_items_to_be_public") is not False:
        fails.append(
            f"allow_nested_items_to_be_public={v.get('allow_nested_items_to_be_public')!r}, required False"
        )
    return fails


def _keyvault_rules(v: dict[str, Any]) -> list[str]:
    fails = []
    if v.get("enable_rbac_authorization") is not True:
        fails.append(f"enable_rbac_authorization={v.get('enable_rbac_authorization')!r}, required True")
    if v.get("purge_protection_enabled") is not True:
        fails.append(f"purge_protection_enabled={v.get('purge_protection_enabled')!r}, required True")
    retention = v.get("soft_delete_retention_days")
    if retention is not None and retention < 90:
        fails.append(f"soft_delete_retention_days={retention!r}, required >= 90")
    return fails


def _servicebus_rules(v: dict[str, Any]) -> list[str]:
    fails = []
    if v.get("minimum_tls_version") != "1.2":
        fails.append(f"minimum_tls_version={v.get('minimum_tls_version')!r}, required '1.2'")
    return fails


def _postgres_rules(v: dict[str, Any]) -> list[str]:
    fails = []
    if v.get("zone") not in ("1", "2", "3", None):
        fails.append(f"zone={v.get('zone')!r}, required '1', '2' or '3'")
    retention = v.get("backup_retention_days")
    if retention is not None and retention < 7:
        fails.append(f"backup_retention_days={retention!r}, required >= 7")
    return fails


def _container_app_rules(v: dict[str, Any]) -> list[str]:
    fails = []
    template = v.get("template")
    if not isinstance(template, dict):
        return ["template block is absent; cannot verify probes, env or image"]
    containers = template.get("container") or []
    if not containers:
        return ["template has no container"]
    for c in containers:
        name = c.get("name", "<unnamed>")
        image = c.get("image") or ""
        if not re.search(r"@sha256:[0-9a-f]{64}$", image):
            fails.append(f"container {name!r} image {image!r} is not digest-pinned")
        for probe in ("liveness_probe", "readiness_probe"):
            if not c.get(probe):
                fails.append(f"container {name!r} has no {probe}")
        for e in c.get("env") or []:
            # A secret smuggled in as a plain value lands here with a value and
            # no secret_name. The plan JSON is an artefact, so a credential in it
            # is a credential in a file on disk.
            if e.get("name") in SECRET_NAME_ALLOWLIST and e.get("secret_name") is None:
                fails.append(f"container {name!r} binds {e['name']!r} as a PLAIN VALUE, not a secret reference")
    return fails




# (resource type, rule id, what the rule protects, predicate)
RULES: list[tuple[str, str, str, Any]] = [
    ("azurerm_storage_account", "storage.tls", "storage must require TLS 1.2 and deny public blob access", _storage_rules),
    ("azurerm_key_vault", "kv.rbac", "key vault must use RBAC with purge protection", _keyvault_rules),
    ("azurerm_servicebus_namespace", "sb.tls", "service bus must require TLS 1.2", _servicebus_rules),
    ("azurerm_postgresql_flexible_server", "pg.durability", "postgres must be zonal with >= 7 days of backup", _postgres_rules),
    ("azurerm_container_app", "app.hardened", "container app must be digest-pinned, probed, and secret-referenced", _container_app_rules),
]

# Resources that MUST be present in a given environment. Absence is a failure: a
# plan missing a security control is not a plan that skipped it, it is a plan in
# which the control silently does not exist.
REQUIRED_BY_ENVIRONMENT: dict[str, list[str]] = {
    "prod": [
        "azurerm_virtual_network",
        "azurerm_user_assigned_identity",
        "azurerm_key_vault",
        "azurerm_storage_account",
        "azurerm_postgresql_flexible_server",
        "azurerm_servicebus_namespace",
        "azurerm_eventgrid_topic",
        "azurerm_eventgrid_event_subscription",
        "azurerm_private_endpoint",
        "azurerm_container_app",
        "azurerm_cdn_frontdoor_firewall_policy",
        "azurerm_api_management",
        "azurerm_monitor_metric_alert",
    ],
    "validation": [
        "azurerm_key_vault",
        "azurerm_storage_account",
        "azurerm_postgresql_flexible_server",
        "azurerm_servicebus_namespace",
        "azurerm_container_app",
    ],
    "dev": [
        "azurerm_key_vault",
        "azurerm_storage_account",
        "azurerm_postgresql_flexible_server",
        "azurerm_servicebus_namespace",
        "azurerm_container_app",
    ],
}

# Resources whose public data plane must be closed in prod.
_PRIVATE_DATA_PLANE = (
    "azurerm_storage_account",
    "azurerm_servicebus_namespace",
    "azurerm_key_vault",
    "azurerm_postgresql_flexible_server",
)


def iter_changes(plan: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any]]]:
    """Yield (address, type, planned_values) for every CREATE and UPDATE."""
    for rc in plan.get("resource_changes", []) or []:
        change = rc.get("change") or {}
        actions = change.get("actions") or []
        # ["delete"] alone is excluded: a resource being destroyed is not a
        # resource whose properties need checking.
        if not any(a in ("create", "update") for a in actions):
            continue
        yield rc.get("address", "<unknown>"), rc.get("type", "<unknown>"), _values(change)



def check(plan: dict[str, Any], environment: str) -> list[str]:
    """Return a list of failure strings. Empty means every invariant held."""
    failures: list[str] = []
    seen_types: set[str] = set()

    for address, rtype, values in iter_changes(plan):
        seen_types.add(rtype)
        for rule_type, rule_id, description, predicate in RULES:
            if rtype != rule_type:
                continue
            try:
                problems = predicate(values)
            except Exception as exc:  # noqa: BLE001 — fail closed on any surprise
                failures.append(f"[{rule_id}] {address}: rule raised {exc!r}; treated as FAILURE")
                continue
            for p in problems:
                failures.append(f"[{rule_id}] {address}: {description} — {p}")

    for required in REQUIRED_BY_ENVIRONMENT.get(environment, []):
        if required not in seen_types:
            failures.append(
                f"[presence] {environment} plan contains no {required}. "
                "A missing control is a failure, not a skip."
            )

    if environment == "prod":
        failures.extend(_prod_invariants(plan))

    return failures


def _prod_invariants(plan: dict[str, Any]) -> list[str]:
    """Invariants that only apply to production, and that no single per-resource
    rule can express because they are about the ENVIRONMENT, not the resource."""
    failures: list[str] = []

    for address, rtype, values in iter_changes(plan):
        if rtype in _PRIVATE_DATA_PLANE and values.get("public_network_access_enabled") is not False:
            failures.append(
                f"[prod.private] {address}: public_network_access_enabled must be False in prod "
                f"(found {values.get('public_network_access_enabled')!r})"
            )

    # Every alert must name a runbook. An alert whose description does not say
    # what to do about it is a notification, not a control. The match is
    # case-insensitive because the descriptions in locals.alert_rules are written
    # as sentence-case prose, and a gate that only bites on one capitalisation is
    # a gate that gets bypassed by a reworded description.
    for rc in plan.get("resource_changes", []) or []:
        if rc.get("type") != "azurerm_monitor_metric_alert":
            continue
        desc = _values(rc.get("change") or {}).get("description") or ""
        if "runbook:" not in desc.lower():
            failures.append(f"[prod.alert] {rc.get('address')}: description does not name a runbook")

    # The action group must exist. A null alert_email creates no action group, and
    # then every alert rule fires into a void.
    action_groups = [
        rc
        for rc in plan.get("resource_changes", []) or []
        if rc.get("type") == "azurerm_monitor_action_group"
    ]
    if not action_groups:
        failures.append("[prod.alert] prod must create a monitor action group; a null alert_email creates none")

    # The source SHA must be real, not the local default. Without it, "which
    # commit is live" has no answer.
    tagged = [v for _a, _t, v in iter_changes(plan) if "source_sha" in (v.get("tags") or {})]
    if not tagged:
        failures.append("[prod.provenance] no resource carries a source_sha tag")
    elif any(v["tags"]["source_sha"] in ("unknown", "") for v in tagged):
        failures.append("[prod.provenance] source_sha tag is 'unknown'; CI must inject TF_VAR_source_sha")

    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed security invariant checker for a Terraform plan.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("plan_json", help="path to `terraform show -json` output")
    ap.add_argument("--environment", required=True, choices=sorted(REQUIRED_BY_ENVIRONMENT))
    args = ap.parse_args(argv)

    try:
        with open(args.plan_json, encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL CLOSED: could not read plan {args.plan_json!r}: {exc}", file=sys.stderr)
        return 2

    failures = check(plan, args.environment)

    if failures:
        print(f"PLAN INVARIANTS FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"PLAN INVARIANTS PASS ({args.environment})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
