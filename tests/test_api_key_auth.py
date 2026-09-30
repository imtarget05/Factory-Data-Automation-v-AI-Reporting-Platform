"""Request-level API-key boundary tests (TDD for fac-api-auth).

Drives the REAL ApiKeyMiddleware through TestClient (httpx present in
.venv-factory), unlike test_auth_boundary.py which only checks source strings.

Auth model (from app/api/security.py — single shared key, no JWT/roles):
- A1 anonymous on protected route -> 401
- A2 wrong key -> 401
- A3 correct key -> through (not 401)
- Safe paths (/, /api/v1/health, /metrics, /docs, /openapi.json) open, no key
- Open mode (env empty): everything through, no key
- N/A by design (documented, not tested): roles/permissions (no roles exist —
  key holder has full access), token expiry/signature (no tokens issued),
  refresh semantics (no refresh flow).
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="API tests need fastapi")
pytest.importorskip("httpx", reason="TestClient needs httpx")
pytest.importorskip("pandas", reason="API needs pandas")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import app.api.main as main  # noqa: E402

TEST_KEY = "fac-auth-test-key"


@pytest.fixture(scope="module")
def client():
    assert main.refresh_data(), "refresh_data failed: no data/raw?"
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture()
def enforced(monkeypatch):
    monkeypatch.setenv("FACTORY_API_KEY", TEST_KEY)


@pytest.fixture()
def open_mode(monkeypatch):
    monkeypatch.delenv("FACTORY_API_KEY", raising=False)


def test_a1_anonymous_protected_rejected(client, enforced):
    r = client.get("/api/v1/kpis")
    assert r.status_code == 401
    assert "X-Factory-API-Key" in r.json()["detail"]


def test_a1_anonymous_post_protected_rejected(client, enforced):
    r = client.post("/api/v1/query", json={"frame": "x"})
    assert r.status_code == 401


def test_a2_wrong_key_rejected(client, enforced):
    r = client.get("/api/v1/kpis", headers={"X-Factory-API-Key": "wrong"})
    assert r.status_code == 401


def test_a3_correct_key_passes_auth_layer(client, enforced):
    r = client.get("/api/v1/kpis", headers={"X-Factory-API-Key": TEST_KEY})
    assert r.status_code != 401


@pytest.mark.parametrize("path", ["/", "/api/v1/health", "/metrics", "/openapi.json", "/docs"])
def test_safe_paths_open_without_key(client, enforced, path):
    r = client.get(path)
    assert r.status_code == 200, path


def test_open_mode_no_key_passes(client, open_mode):
    r = client.get("/api/v1/kpis")
    assert r.status_code != 401


def test_safe_prefix_must_not_bypass_sibling_path(client, enforced):
    """A path that merely STARTS WITH a safe prefix is not safe.

    /metrics-evil must be challenged (401), not waved through to the router.
    """
    r = client.get("/metrics-evil")
    assert r.status_code == 401
