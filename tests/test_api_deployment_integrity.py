"""Regression tests for deployment-integrity health semantics.

P1 root cause: `data/raw/*` is gitignored, so an image built from a clean
clone ships an empty data/raw. `refresh_data()` set `_datasets = {}` and
`/api/v1/health` reported `data_loaded: _datasets is not None`, which is True
for an empty dict. The container HEALTHCHECK therefore stayed green while
/api/v1/kpis, /api/v1/alerts and /api/v1/report all raised 500, and
/api/v1/data answered 200 {"datasets": {}}.

These tests pin the corrected contract:
  no data loaded  -> health 503 / data_up 0 / business endpoints 503
  data loaded     -> health 200 / data_up 1 / business endpoints 200

Evidence: docs/evidence/factory_p1_triage.md
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import main as api_main

BUSINESS_ENDPOINTS = [
    "/api/v1/data",
    "/api/v1/kpis",
    "/api/v1/alerts",
    "/api/v1/report",
]


@pytest.fixture
def client():
    return TestClient(api_main.app)


@pytest.fixture(autouse=True)
def restore_globals():
    """The module caches ETL output in globals; never leak state between tests."""
    saved = (api_main._datasets, api_main._kpis, api_main._alerts)
    yield
    api_main._datasets, api_main._kpis, api_main._alerts = saved


@pytest.fixture
def empty_deployment(monkeypatch):
    """Simulate the Azure failure: ETL finds no source files."""
    monkeypatch.setattr(api_main, "run_etl", lambda *a, **k: {})
    api_main._datasets, api_main._kpis, api_main._alerts = {}, None, None
    return {}


@pytest.fixture
def populated_deployment(monkeypatch):
    """Simulate a healthy deployment without running the real ETL."""
    import pandas as pd

    frame = pd.DataFrame({"a": [1, 2, 3]})
    monkeypatch.setattr(api_main, "run_etl", lambda *a, **k: {"production": frame})
    monkeypatch.setattr(
        api_main,
        "calculate_all_kpis",
        lambda ds: {"daily_production": pd.DataFrame({"Date": ["d1"], "v": [1]})},
    )
    monkeypatch.setattr(api_main, "AlertManager", lambda *a, **k: type(
        "AM", (), {"check_all": staticmethod(lambda d, kp: [])})())
    api_main._datasets, api_main._kpis, api_main._alerts = None, None, None
    return {"production": frame}


# --- data_is_loaded ---------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [(None, False), ({}, False), ({"a": 1}, True)],
    ids=["none", "empty-dict", "non-empty"],
)
def test_data_is_loaded_rejects_empty_dict(value, expected):
    """The bug: `is not None` treats {} as loaded. bool() must not."""
    api_main._datasets = value
    assert api_main.data_is_loaded() is expected


# --- empty deployment -------------------------------------------------------

def test_health_is_503_when_no_data(client, empty_deployment):
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["data_loaded"] is False


def test_metrics_report_zero_when_no_data(client, empty_deployment):
    """factory_data_up must be 0, not 1. This is the P0 silent-pass signal."""
    body = client.get("/metrics").text
    up = [line for line in body.splitlines() if line.startswith("factory_data_up ")]
    assert up == ["factory_data_up 0"]


@pytest.mark.parametrize("endpoint", BUSINESS_ENDPOINTS)
def test_business_endpoints_503_not_500_when_no_data(client, empty_deployment, endpoint):
    """A missing dataset is a service-readiness problem (503), not a crash (500)."""
    response = client.get(endpoint)
    assert response.status_code == 503, response.text
    assert "data/raw" in response.json()["detail"]


def test_data_endpoint_never_answers_200_with_empty_payload(client, empty_deployment):
    """Regression for the silent failure: 200 {"datasets": {}}."""
    response = client.get("/api/v1/data")
    assert response.status_code != 200
    assert response.json() != {"datasets": {}}


def test_refresh_data_reports_failure_and_clears_cache(empty_deployment):
    """An empty reload must not leave a stale KPI cache for a later caller."""
    assert api_main.refresh_data() is False
    assert api_main._kpis is None
    assert api_main._alerts is None


# --- populated deployment ---------------------------------------------------

def test_health_is_200_when_data_loaded(client, populated_deployment):
    assert api_main.refresh_data() is True
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["data_loaded"] is True


def test_metrics_report_one_when_data_loaded(client, populated_deployment):
    api_main.refresh_data()
    body = client.get("/metrics").text
    assert "factory_data_up 1" in body


@pytest.mark.parametrize("endpoint", ["/api/v1/data", "/api/v1/kpis", "/api/v1/alerts"])
def test_business_endpoints_200_when_data_loaded(client, populated_deployment, endpoint):
    api_main.refresh_data()
    assert client.get(endpoint).status_code == 200
