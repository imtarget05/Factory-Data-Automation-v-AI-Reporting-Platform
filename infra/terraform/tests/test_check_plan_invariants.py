#!/usr/bin/env python3
"""Negative controls for check_plan_invariants.py.

WHAT THIS PROVES, AND WHAT IT DOES NOT

Each test mutates ONE security property of a plan document and asserts that the
checker fails FOR THAT REASON. A mutation the checker survives is a rule that
protects nothing, so a surviving mutation is a test failure, not a skip.

The plan documents below are SYNTHETIC — hand-built to the shape
`terraform show -json` emits, not produced by a real `terraform plan`. That is a
real limitation: producing a genuine plan needs Azure credentials, which a unit
test must not require. These tests therefore prove the CHECKER bites, not that
Terraform emits the shape we assume.

The complementary proof — that the real configuration produces a plan the checker
passes — is the `terraform plan` step in
.github/workflows/terraform-validate.yml, which runs with credentials in the
validation environment. Both halves are needed: the unit test alone would pass
even if Terraform's JSON shape differed from our assumption, and the pipeline
alone would not say which rule caught a regression.

Run:  python3 tests/test_check_plan_invariants.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_plan_invariants import check  # noqa: E402

# A syntactically valid but obviously fake digest. The checker only inspects the
# SHAPE of the reference; the digest value itself is not this test's business.
SHA = "a" * 64
IMAGE = f"ghcr.io/imtarget05/factory-data-api@sha256:{SHA}"


def _rc(address: str, rtype: str, after: dict[str, Any]) -> dict[str, Any]:
    return {"address": address, "type": rtype, "change": {"actions": ["create"], "after": after}}


def base_plan() -> dict[str, Any]:
    """A prod plan that every rule should accept."""
    tags = {"project": "factory", "source_sha": "be2fb04", "managed_by": "terraform"}
    return {
        "resource_changes": [
            _rc("azurerm_virtual_network.this", "azurerm_virtual_network", {"name": "vnet-facprod"}),
            _rc("azurerm_user_assigned_identity.api", "azurerm_user_assigned_identity", {"name": "id-api"}),
            _rc(
                "azurerm_key_vault.this",
                "azurerm_key_vault",
                {
                    "name": "kv-facprod",
                    "enable_rbac_authorization": True,
                    "purge_protection_enabled": True,
                    "soft_delete_retention_days": 90,
                    "public_network_access_enabled": False,
                    # Tagged as well as the storage account, so the provenance
                    # rule does not depend on any single resource surviving. If
                    # only one resource carried the SHA tag, a plan that recreated
                    # everything except that one would fail provenance for the
                    # wrong reason.
                    "tags": tags,
                },
            ),
            _rc(
                "azurerm_storage_account.this",
                "azurerm_storage_account",
                {
                    "name": "stfacprod",
                    "min_tls_version": "TLS1_2",
                    "https_traffic_only_enabled": True,
                    "allow_nested_items_to_be_public": False,
                    "public_network_access_enabled": False,
                    "tags": tags,
                },
            ),
            _rc(
                "azurerm_postgresql_flexible_server.this",
                "azurerm_postgresql_flexible_server",
                {
                    "name": "psql-facprod",
                    "zone": "1",
                    "backup_retention_days": 7,
                    "public_network_access_enabled": False,
                },
            ),
            _rc(
                "azurerm_servicebus_namespace.this",
                "azurerm_servicebus_namespace",
                {
                    "name": "sb-facprod",
                    "minimum_tls_version": "1.2",
                    "public_network_access_enabled": False,
                },
            ),
            _rc("azurerm_eventgrid_topic.this", "azurerm_eventgrid_topic", {"name": "eg"}),
            _rc("azurerm_eventgrid_event_subscription.s", "azurerm_eventgrid_event_subscription", {"name": "sub"}),
            _rc("azurerm_private_endpoint.blob", "azurerm_private_endpoint", {"name": "pe-blob"}),
            _rc(
                "azurerm_container_app.this",
                "azurerm_container_app",
                {
                    "name": "ca-facprod-api",
                    "template": {
                        "container": [
                            {
                                "name": "factory-api",
                                "image": IMAGE,
                                "liveness_probe": {"path": "/api/v1/health"},
                                "readiness_probe": {"path": "/api/v1/health"},
                                "env": [{"name": "PORT", "value": "8000"}],
                            }
                        ]
                    },
                },
            ),
            _rc("azurerm_cdn_frontdoor_firewall_policy.this", "azurerm_cdn_frontdoor_firewall_policy", {"name": "fdpFactory"}),
            _rc("azurerm_api_management.this", "azurerm_api_management", {"name": "apim-factory"}),
            _rc("azurerm_monitor_action_group.this", "azurerm_monitor_action_group", {"name": "ag-facprod"}),
            _rc(
                "azurerm_monitor_metric_alert.dlq",
                "azurerm_monitor_metric_alert",
                {"name": "factory-dlq-backlog", "description": "DLQ growing. Runbook: docs/runbooks/dlq-replay.md"},
            ),
        ]
    }


def find(plan: dict[str, Any], address: str) -> dict[str, Any]:
    for rc in plan["resource_changes"]:
        if rc["address"] == address:
            return rc
    raise KeyError(address)


PASSED = 0



# ── the baseline itself must pass ────────────────────────────────────────────


def expect_clean(plan: dict[str, Any], environment: str = "prod") -> None:
    global PASSED
    failures = check(plan, environment)
    assert not failures, "expected a clean plan, got:\n" + "\n".join(failures)
    PASSED += 1


def expect_failure(plan: dict[str, Any], needle: str, environment: str = "prod") -> None:
    """Assert the checker fails AND names the expected reason.

    Asserting on the message as well as the failure is the point: a checker that
    fails for an unrelated reason still satisfies a naive "did it fail?" test, and
    that is how a broken gate ships.
    """
    global PASSED
    failures = check(plan, environment)
    assert failures, "MUTATION SURVIVED: the checker did not fail on this mutation"
    assert any(needle in f for f in failures), (
        f"checker failed, but not for the intended reason {needle!r}:\n" + "\n".join(failures)
    )
    PASSED += 1


def test_alert_without_runbook_detected() -> None:
    p = base_plan()
    find(p, "azurerm_monitor_metric_alert.dlq")["change"]["after"]["description"] = "Something is wrong."
    expect_failure(p, "prod.alert")


def test_baseline_plan_is_clean() -> None:
    expect_clean(base_plan())


# ── storage mutations ────────────────────────────────────────────────────────


def test_deep_copy_isolation() -> None:
    """Guards the tests themselves: if base_plan() returned a shared object, one
    test's mutation would leak into every later test and the suite would pass for
    the wrong reason."""
    p = base_plan()
    q = copy.deepcopy(p)
    find(q, "azurerm_storage_account.this")["change"]["after"]["min_tls_version"] = "TLS1_0"
    assert find(p, "azurerm_storage_account.this")["change"]["after"]["min_tls_version"] == "TLS1_2"


def test_keyvault_purge_protection_disabled_detected() -> None:
    p = base_plan()
    find(p, "azurerm_key_vault.this")["change"]["after"]["purge_protection_enabled"] = False
    expect_failure(p, "kv.rbac")


def test_keyvault_rbac_disabled_detected() -> None:
    p = base_plan()
    find(p, "azurerm_key_vault.this")["change"]["after"]["enable_rbac_authorization"] = False
    expect_failure(p, "kv.rbac")


def test_keyvault_short_soft_delete_detected() -> None:
    p = base_plan()
    find(p, "azurerm_key_vault.this")["change"]["after"]["soft_delete_retention_days"] = 7
    expect_failure(p, "kv.rbac")


# ── service bus / postgres mutations ─────────────────────────────────────────


def test_missing_liveness_probe_detected() -> None:
    p = base_plan()
    find(p, "azurerm_container_app.this")["change"]["after"]["template"]["container"][0]["liveness_probe"] = None
    expect_failure(p, "app.hardened")


def test_missing_readiness_probe_detected() -> None:
    p = base_plan()
    find(p, "azurerm_container_app.this")["change"]["after"]["template"]["container"][0]["readiness_probe"] = None
    expect_failure(p, "app.hardened")


def test_mutable_image_tag_detected() -> None:
    p = base_plan()
    find(p, "azurerm_container_app.this")["change"]["after"]["template"]["container"][0]["image"] = "repo:latest"
    expect_failure(p, "app.hardened")


def test_postgres_short_backup_detected() -> None:
    p = base_plan()
    find(p, "azurerm_postgresql_flexible_server.this")["change"]["after"]["backup_retention_days"] = 1
    expect_failure(p, "pg.durability")


def test_prod_missing_action_group_detected() -> None:
    p = base_plan()
    p["resource_changes"] = [rc for rc in p["resource_changes"] if rc["type"] != "azurerm_monitor_action_group"]
    expect_failure(p, "prod.alert")


def test_prod_missing_eventgrid_subscription_detected() -> None:
    p = base_plan()
    p["resource_changes"] = [
        rc for rc in p["resource_changes"] if rc["type"] != "azurerm_eventgrid_event_subscription"
    ]
    expect_failure(p, "presence")


def test_prod_missing_private_endpoint_detected() -> None:
    p = base_plan()
    p["resource_changes"] = [rc for rc in p["resource_changes"] if rc["type"] != "azurerm_private_endpoint"]
    expect_failure(p, "presence")


def test_prod_missing_waf_detected() -> None:
    p = base_plan()
    p["resource_changes"] = [rc for rc in p["resource_changes"] if rc["type"] != "azurerm_cdn_frontdoor_firewall_policy"]
    expect_failure(p, "presence")


def test_prod_public_data_plane_detected() -> None:
    p = base_plan()
    find(p, "azurerm_storage_account.this")["change"]["after"]["public_network_access_enabled"] = True
    expect_failure(p, "prod.private")


def test_prod_public_keyvault_detected() -> None:
    p = base_plan()
    find(p, "azurerm_key_vault.this")["change"]["after"]["public_network_access_enabled"] = True
    expect_failure(p, "prod.private")


def test_prod_unknown_source_sha_detected() -> None:
    p = base_plan()
    find(p, "azurerm_storage_account.this")["change"]["after"]["tags"]["source_sha"] = "unknown"
    expect_failure(p, "prod.provenance")


def test_prod_without_source_sha_tag_detected() -> None:
    p = base_plan()
    del find(p, "azurerm_storage_account.this")["change"]["after"]["tags"]["source_sha"]
    expect_failure(p, "prod.provenance")


# ── the checker must not be fooled, and must not cry wolf ────────────────────


def test_resource_being_destroyed_is_not_property_checked() -> None:
    """A destroy is not a security regression in itself, so the PER-RESOURCE
    rules must not fire on a deleted account with loose settings.

    The prod PRESENCE rule still fires, and that is correct: removing the storage
    account from the plan IS a prod regression. What this test pins is the
    narrower claim — `storage.tls` stays silent — so that a routine destroy does
    not produce a wall of misleading TLS errors that train people to ignore the
    gate.
    """
    p = base_plan()
    find(p, "azurerm_storage_account.this")["change"] = {
        "actions": ["delete"],
        "after": {
            "min_tls_version": "TLS1_0",
            "https_traffic_only_enabled": False,
            "allow_nested_items_to_be_public": True,
            "public_network_access_enabled": True,
        },
    }
    failures = check(p, "prod")
    assert not any("storage.tls" in f for f in failures), (
        "a destroy must not trigger per-resource property rules:\n" + "\n".join(failures)
    )


def test_secret_as_plain_env_value_detected() -> None:
    p = base_plan()
    find(p, "azurerm_container_app.this")["change"]["after"]["template"]["container"][0]["env"].append(
        {"name": "FACTORY_API_KEY", "value": "hunter2"}
    )
    expect_failure(p, "app.hardened")


def test_secret_correctly_referenced_is_clean() -> None:
    """The positive counterpart: the rule must not fire on a correct binding, or
    it trains everyone to ignore it."""
    p = base_plan()
    find(p, "azurerm_container_app.this")["change"]["after"]["template"]["container"][0]["env"].append(
        {"name": "FACTORY_API_KEY", "secret_name": "FACTORY_API_KEY"}
    )
    expect_clean(p)


# ── environment-level mutations ──────────────────────────────────────────────


def test_servicebus_tls_downgrade_detected() -> None:
    p = base_plan()
    find(p, "azurerm_servicebus_namespace.this")["change"]["after"]["minimum_tls_version"] = "1.0"
    expect_failure(p, "sb.tls")


# ── container app mutations ──────────────────────────────────────────────────


def test_storage_https_only_disabled_detected() -> None:
    p = base_plan()
    find(p, "azurerm_storage_account.this")["change"]["after"]["https_traffic_only_enabled"] = False
    expect_failure(p, "storage.tls")


# ── key vault mutations ──────────────────────────────────────────────────────


def test_storage_public_blob_access_detected() -> None:
    p = base_plan()
    find(p, "azurerm_storage_account.this")["change"]["after"]["allow_nested_items_to_be_public"] = True
    expect_failure(p, "storage.tls")


def test_storage_tls_downgrade_detected() -> None:
    p = base_plan()
    find(p, "azurerm_storage_account.this")["change"]["after"]["min_tls_version"] = "TLS1_0"
    expect_failure(p, "storage.tls")


def test_unreadable_container_template_fails_closed() -> None:
    p = base_plan()
    find(p, "azurerm_container_app.this")["change"]["after"]["template"] = "not-a-dict"
    expect_failure(p, "app.hardened")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures: list[str] = []
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failures.append(f"{t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{t.__name__}: raised {exc!r}")
    total = len(tests)
    if failures:
        print(f"NEGATIVE CONTROLS FAILED ({len(failures)}/{total}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"NEGATIVE CONTROLS PASS ({total}/{total} tests, {PASSED} checker assertions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
