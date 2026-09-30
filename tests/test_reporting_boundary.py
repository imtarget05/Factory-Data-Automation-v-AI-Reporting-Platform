"""Reporting boundary: the HTTP/serialization surface of the quality-gated
AI report (Phase C).

Guards two things the gate alone cannot:
1. The gate decision survives the transport — every leaf that leaves
   /api/v1/report is a JSON-native type. (Real regression: numpy.int64 inside
   the evidence made FastAPI's encoder raise, so the endpoint returned 500
   instead of a report or an explicit block.)
2. A BLOCKED report is a well-formed 200 payload with `status: BLOCKED`,
   never an exception — and the LLM is not invoked.
"""

import csv
import json
import logging
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
from test_ai_quality_gate import FakeLLM, make_datasets, make_generator, make_kpis  # noqa: E402

import app.api.main as main  # noqa: E402
from app.ai.reporting import AIReportGenerator, _json_safe  # noqa: E402
from app.data_contracts.quality_gate import evaluate_quality  # noqa: E402

_JSON_NATIVE = (bool, int, float, str, type(None))


def _assert_json_native(obj, path="report"):
    """Fail on any non-JSON-native leaf (numpy scalar, DataFrame, Timestamp...)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert isinstance(k, str), f"non-str key at {path}: {type(k).__name__}"
            _assert_json_native(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_json_native(v, f"{path}[{i}]")
    else:
        assert isinstance(obj, _JSON_NATIVE), (
            f"non-JSON-native leaf at {path}: {type(obj).__name__}"
        )
        if isinstance(obj, float):
            import math

            assert math.isfinite(obj), f"non-finite float at {path}"


@pytest.fixture(scope="module")
def client():
    assert main.refresh_data(), "refresh_data failed: no data/raw?"
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _open_mode(monkeypatch):
    monkeypatch.delenv("FACTORY_API_KEY", raising=False)


# ------------------------------------------------------- transport safety --


def test_report_endpoint_returns_json_native_payload(client, monkeypatch):
    """No numpy/DataFrame may cross the HTTP boundary (was a 500)."""
    monkeypatch.setattr("app.ai.reporting.get_llm", lambda: FakeLLM(available=False))
    r = client.get("/api/v1/report")
    assert r.status_code == 200, r.text[:200]
    report = AIReportGenerator().generate_report(
        main._kpis, [], main._datasets, quarantine=main._quality_context(main._datasets)
    )
    _assert_json_native(report["evidence"], "evidence")
    _assert_json_native(report["quality"], "quality")
    json.dumps(report, allow_nan=False)  # strict: no NaN/Infinity tokens
    assert r.json()["evidence"]["snapshot_id"] == report["evidence"]["snapshot_id"]


def test_json_safe_coerces_numpy_nan_and_frames():
    np = pytest.importorskip("numpy")
    import pandas as pd

    assert _json_safe(np.int64(7)) == 7
    assert isinstance(_json_safe(np.int64(7)), int)
    assert _json_safe(np.float32(1.5)) == pytest.approx(1.5)
    assert _json_safe(float("nan")) is None
    assert _json_safe(float("inf")) is None
    assert _json_safe({1, 2, 3}) == ["1", "2", "3"]
    frame = pd.DataFrame({"a": np.array([1, 2]), "b": ["x", "y"]})
    coerced = _json_safe(frame)
    assert coerced["rows"] == 2 and coerced["sample"][0]["a"] == 1
    ts = _json_safe(pd.Timestamp("2026-09-30"))
    assert isinstance(ts, str) and ts.startswith("2026-09-30")
    nested = {
        "b": np.int64(1),
        "a": {"z": float("nan")},
    }
    assert list(_json_safe(nested).keys()) == ["a", "b"]  # deterministic order
    json.dumps(_json_safe({"k": np.int64(3), "n": float("nan")}), allow_nan=False)


def test_real_data_reports_are_deterministic_modulo_audit_stamp(client):
    """Same inputs => same evidence snapshot and same canonical content.

    Only `evaluated_at_epoch` (wall clock, by design) is excluded. This is NOT
    a claim that the whole HTTP response is byte-identical: it is a claim that
    business evidence and quality-decision content are a pure function of the
    input data, with evaluation time isolated as metadata.
    """
    import hashlib

    volatile = {"evaluated_at_epoch", "timestamp", "generated_at", "now", "date"}

    def canonical(obj):
        if isinstance(obj, dict):
            return {k: canonical(v) for k, v in sorted(obj.items()) if k not in volatile}
        if isinstance(obj, list):
            return [canonical(v) for v in obj]
        return obj

    payloads = []
    for _ in range(2):
        rep = AIReportGenerator().generate_report(
            main._kpis, [], main._datasets, quarantine=main._quality_context(main._datasets)
        )
        blob = json.dumps(
            canonical(
                {
                    "evidence": rep["evidence"],
                    "quality": rep["quality"],
                    "provenance": rep["provenance"],
                    "mode": rep["generation_mode"],
                    "status": rep["status"],
                }
            ),
            sort_keys=True,
            allow_nan=False,
        )
        payloads.append((rep["evidence"]["snapshot_id"], blob))

    assert payloads[0][0] == payloads[1][0], "snapshot_id must be input-derived"
    assert (
        hashlib.sha256(payloads[0][1].encode()).hexdigest()
        == hashlib.sha256(payloads[1][1].encode()).hexdigest()
    )


def test_quarantine_rate_scoped_to_current_run_not_cumulative_dlq(client, monkeypatch, tmp_path):
    """The DLQ file is append-only; the gate rate must not use its lifetime total.

    Regression: `_quality_context` divided every row ever written to
    corrupt_records.csv by the current run's surviving rows. After 33 ETL runs
    the cumulative total exceeded the per-run count and the gate returned BAD
    with "quarantine rate 0.555 exceeds 0.5" on perfectly clean data — a report
    blocked by history rather than by the batch. The rate now comes from
    run-scoped counters that `load_and_clean_all` resets at the start of each run.
    """
    from app.etl import quarantine as q

    # A DLQ file carrying decades of history, far more rows than one run sees.
    huge = tmp_path / "corrupt_records.csv"
    with open(huge, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(q.QUARANTINE_COLUMNS)
        for i in range(5000):
            w.writerow(["2020-01-01T00:00:00", "production", "production.csv",
                        i, "Target_Qty", "-5", "greater_than_equal"])
    monkeypatch.setattr(q, "DATA_QUARANTINE_FILE", str(huge), raising=False)
    monkeypatch.setattr("app.api.main.quarantine_summary",
                        lambda: dict(q.quarantine_summary(str(huge))))
    monkeypatch.setattr("app.api.main.quarantine_run_summary",
                        lambda: q.quarantine_run_summary())

    assert main.refresh_data(), "ETL produced no datasets"

    ctx = main._quality_context(main._datasets)
    assert ctx["scope"] == "current_etl_run"
    assert ctx["dlq_cumulative_rows"] >= 5000, "history is still counted, only for reporting"
    assert ctx["rejected"] < ctx["dlq_cumulative_rows"] // 10, (
        "rejected must be this run's rejects, not the file's lifetime total")

    report = AIReportGenerator().generate_report(
        main._kpis, [], main._datasets, quarantine=ctx)
    assert report["quality"]["status"] == "GOOD", report["quality"]["reason"]
    rate_check = next(c for c in report["quality"]["checks"]
                      if c["name"] == "quarantine_rate")
    assert rate_check["ok"] is True
    assert "scope=current_etl_run" in rate_check["detail"]


def test_absent_run_counters_are_not_reported_as_a_clean_zero_rate():
    """No ETL in-process means unknown, not zero."""
    d = evaluate_quality(datasets=make_datasets(), kpis=make_kpis(),
                         quarantine={"passed": 100, "rejected": None,
                                     "scope": "not_provided"})
    qc = next(c for c in d.checks if c["name"] == "quarantine_rate")
    assert "not_provided" in qc["detail"]
    assert "rate=" not in qc["detail"], "an unknown count must not print a rate"


# ------------------------------------------------------ gate over HTTP -----


def test_fallback_report_does_not_count_missing_citations(monkeypatch):
    """A deterministic fallback cites nothing: that is not a provenance breach."""
    fake = FakeLLM(available=False)
    gen = make_generator(fake, monkeypatch)
    out = gen.generate_report(make_kpis(), [], make_datasets())
    assert out["generation_mode"] == "FALLBACK"
    assert out["provenance_rejected"] == 0
    assert out["provenance"] == out["evidence"]["source_ids"]


def test_quarantine_dlq_feeds_the_gate(client):
    """_quality_context translates the row-level DLQ into gate input."""
    ctx = main._quality_context(main._datasets)
    assert set(("passed", "rejected", "by_dataset")) <= set(ctx)
    assert ctx["passed"] > 0
    assert ctx["rejected"] >= 0


def test_blocked_report_is_well_formed_200_not_500(client, monkeypatch):
    monkeypatch.setattr("app.ai.reporting.get_llm", lambda: FakeLLM(available=False))
    monkeypatch.setattr(main, "_quality_context", lambda ds: {"passed": 1, "rejected": 99})
    r = client.get("/api/v1/report")
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["status"] == "BLOCKED"
    assert body["generation_mode"] == "NOT_RUN"
    assert body["quality"]["status"] == "BAD"
    assert body["evidence"] is None
    assert body["provenance"] == []


def test_blocked_report_never_invokes_the_llm_over_http(client, monkeypatch):
    fake = FakeLLM(payload={"title": "should not run"})
    monkeypatch.setattr("app.ai.reporting.get_llm", lambda: fake)
    monkeypatch.setattr(main, "_quality_context", lambda ds: {"passed": 1, "rejected": 99})
    r = client.get("/api/v1/report")
    assert r.status_code == 200
    assert fake.calls == 0, "LLM was invoked on a BLOCKED batch over HTTP"
    assert r.json()["status"] == "BLOCKED"


def test_good_batch_does_invoke_the_llm_over_http(client, monkeypatch):
    fake = FakeLLM(payload={"title": "Daily report", "summary": "ok"})
    monkeypatch.setattr("app.ai.reporting.get_llm", lambda: fake)
    monkeypatch.setattr(main, "_quality_context", lambda ds: {"passed": 100, "rejected": 0})
    r = client.get("/api/v1/report")
    assert r.status_code == 200
    assert fake.calls == 1
    assert r.json()["generation_mode"] == "REAL_MODEL"


# ------------------------------------------------------------ observability --


def test_quality_gate_and_block_are_logged(monkeypatch, caplog):
    """The gate decision and every block are auditable through the existing
    structured logger — no parallel logging framework."""
    fake = FakeLLM()
    gen = make_generator(fake, monkeypatch)
    kpis = make_kpis()
    kpis["daily_production"].loc[0, "Achievement_Rate_pct"] = float("nan")
    with caplog.at_level(logging.INFO, logger="ai"):
        gen.generate_report(kpis, [], make_datasets())
    messages = [rec.getMessage() for rec in caplog.records if rec.name == "ai"]
    assert "quality_gate_decision" in messages
    assert "report_blocked" in messages
    assert "report_provenance" not in messages  # blocked run emits no provenance
