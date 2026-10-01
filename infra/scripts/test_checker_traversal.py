#!/usr/bin/env python3
"""Unit tests for check_invariants AST walker traversal."""
import sys
from pathlib import Path

# Add infra to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_invariants import _walk_resources, Unsupported


def test_walk_dict_resources():
    sample = {
        "res1": {
            "type": "Microsoft.KeyVault/vaults",
            "name": "test-kv"
        },
        "res2": {
            "type": "Microsoft.Resources/deployments",
            "properties": {
                "template": {
                    "resources": [
                        {
                            "type": "Microsoft.Storage/storageAccounts",
                            "name": "teststorage"
                        }
                    ]
                }
            }
        }
    }
    nodes = list(_walk_resources(sample, "$.resources"))
    assert len(nodes) == 3
    types = [n[0]["type"] for n in nodes]
    assert "Microsoft.KeyVault/vaults" in types
    assert "Microsoft.Resources/deployments" in types
    assert "Microsoft.Storage/storageAccounts" in types
    print("test_walk_dict_resources passed")


def test_walk_list_resources():
    sample = [
        {
            "type": "Microsoft.KeyVault/vaults",
            "name": "test-kv"
        }
    ]
    nodes = list(_walk_resources(sample, "$.resources"))
    assert len(nodes) == 1
    assert nodes[0][0]["type"] == "Microsoft.KeyVault/vaults"
    print("test_walk_list_resources passed")


if __name__ == "__main__":
    test_walk_dict_resources()
    test_walk_list_resources()
    print("All traversal tests passed!")
