"""FDA-021-025: POST /api/v1/query endpoint tests (additive route).

Covers: valid spec -> 200 with rows; DELETE/DROP frame -> 422 (never 500);
unknown frame/metric -> 422; top_n bomb capped at MAX_ROWS; timeout clamped
and respected; malformed bodies -> 422, never 500.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi", reason="query API needs fastapi")
pytest.importorskip("httpx", reason="TestClient needs httpx")
pytest.importorskip("pandas", reason="query API needs pandas")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import app.api.main as main  # noqa: E402
from app.ai.sql_tool import MAX_ROWS  # noqa: E402


@pytest.fixture(scope="module")
def client():
    assert main.refresh_data(), "refresh_data failed: no data/raw?"
    return TestClient(main.app, raise_server_exceptions=False)


VALID_SPEC = {
    "frame": "machine_utilization",
    "metric": "Total_Downtime",
    "group_by": ["Machine_ID"],
    "agg": "sum",
    "top_n": 5,
}


def test_valid_spec_returns_200_with_rows(client):
    r = client.post("/api/v1/query", json={"spec": VALID_SPEC})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == len(body["rows"]) > 0
    assert "sum_Total_Downtime" in body["rows"][0]


def test_bare_spec_body_also_works(client):
    r = client.post("/api/v1/query", json=dict(VALID_SPEC))
    assert r.status_code == 200, r.text
    assert r.json()["rows"]


def test_delete_is_rejected_422_not_500(client):
    r = client.post("/api/v1/query", json={"spec": {"frame": "DELETE FROM kpis", "metric": "x"}})
    assert r.status_code == 422, r.text


def test_drop_is_rejected_422_not_500(client):
    r = client.post(
        "/api/v1/query", json={"spec": {"frame": "DROP TABLE daily_production", "metric": "x"}}
    )
    assert r.status_code == 422, r.text


def test_unknown_frame_422(client):
    r = client.post(
        "/api/v1/query", json={"spec": {"frame": "nope", "metric": "x", "group_by": []}}
    )
    assert r.status_code == 422, r.text


def test_unknown_metric_422(client):
    r = client.post(
        "/api/v1/query",
        json={"spec": {"frame": "daily_production", "metric": "DROP TABLE x", "group_by": []}},
    )
    assert r.status_code == 422, r.text


def test_top_n_bomb_is_capped(client):
    spec = dict(VALID_SPEC, top_n=500)
    r = client.post("/api/v1/query", json={"spec": spec})
    assert r.status_code == 200, r.text
    assert r.json()["count"] <= MAX_ROWS


def test_timeout_clamped_and_respected(client):
    r = client.post("/api/v1/query", json={"spec": VALID_SPEC, "timeout": 9999})
    assert r.status_code == 200, r.text  # clamped to 30s, fast query passes
    r = client.post("/api/v1/query", json={"spec": VALID_SPEC, "timeout": "bad"})
    assert r.status_code == 422, r.text


def test_malformed_bodies_never_500(client):
    for body in (
        {"spec": "DROP TABLE x"},
        {"spec": {"frame": "daily_production"}},
        {"foo": "bar"},
        {"spec": {"frame": "daily_production", "metric": "Total_Actual",
                   "group_by": ["Date"], "agg": "eval"}},
    ):
        r = client.post("/api/v1/query", json=body)
        assert r.status_code in (200, 422), f"{body}: got {r.status_code}"
        assert r.status_code != 500


def test_existing_routes_untouched(client):
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/kpis").status_code == 200


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
