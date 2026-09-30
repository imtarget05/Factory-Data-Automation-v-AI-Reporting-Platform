"""Phase C fail-closed tests: data-quality gate authorizes AI reporting.

Invariants under test:
- GOOD quality  -> report path may run (LLM called at most once).
- BAD quality   -> report BLOCKED, llm call count == 0.
- UNKNOWN/error -> report BLOCKED (fail closed, never silently GOOD).
- The LLM cannot override the quality decision or the structured evidence.
- Provenance is deterministic set-membership against authorized evidence ids.
- generation_mode honestly distinguishes REAL_MODEL / FALLBACK / NOT_RUN.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.data_contracts.quality_gate import (  # noqa: E402
    BAD,
    GOOD,
    UNKNOWN,
    evaluate_quality,
)

pd = pytest.importorskip("pandas")


# ---------------------------------------------------------------- fixtures --

class FakeLLM:
    """Deterministic test double. `calls` proves when the LLM was invoked."""

    def __init__(self, payload=None, available=True):
        self.calls = 0
        self.payload = payload if payload is not None else {"title": "T"}
        self._available = available

    @property
    def available(self):
        return self._available

    def generate_json(self, prompt, system_prompt=None, **kw):
        self.calls += 1
        return self.payload

    def generate(self, prompt, system_prompt=None, temperature=0.3, **kw):
        self.calls += 1
        return "ok"


def make_datasets():
    dates = pd.to_datetime(["2026-09-28", "2026-09-29", "2026-09-30"])
    return {
        "production": pd.DataFrame({
            "Date": dates, "Line": ["L1"] * 3, "Target_Qty": [100] * 3,
            "Actual_Qty": [95, 92, 90], "Good_Qty": [90, 88, 85],
            "Reject_Qty": [5, 4, 5], "Cycle_Time_sec": [12.0] * 3}),
        "quality": pd.DataFrame({
            "Date": dates, "Defect_Count": [3, 4, 5], "Inspected_Qty": [100] * 3}),
        "machine": pd.DataFrame({
            "Date": dates, "Machine_ID": ["M-01"] * 3, "Status": ["RUN"] * 3,
            "Downtime_min": [10.0, 5.0, 8.0], "Speed_RPM": [1000.0] * 3,
            "Temperature_C": [60.0] * 3, "Vibration_mm": [1.0] * 3,
            "Power_Usage_pct": [70.0] * 3}),
        "inventory": pd.DataFrame({
            "Date": dates, "Product": ["A"] * 3, "Stock_Qty": [500] * 3,
            "Reorder_Point": [100] * 3, "Unit_Price": [10.0] * 3}),
    }


def make_kpis():
    daily = pd.DataFrame({
        "Date": ["2026-09-30"], "Total_Target": [300], "Total_Actual": [277],
        "Achievement_Rate_pct": [92.3], "Reject_Rate_pct": [4.5],
        "Yield_pct": [95.5]})
    return {
        "daily_production": daily,
        "weekly_production": daily,
        "monthly_production": daily,
        "oee": pd.DataFrame({"Date": ["2026-09-30"], "OEE_pct": [81.2],
                             "Availability_pct": [90.0], "Performance_pct": [95.0],
                             "Quality_pct": [95.5]}),
        "machine_utilization": pd.DataFrame({
            "Date": ["2026-09-30"], "Machine_ID": ["M-01"], "Failure_Count": [0],
            "Total_Downtime": [8.0], "Utilization_pct": [88.0]}),
        "inventory_kpi": pd.DataFrame({
            "Total_Stock": [500], "Stock_Value": [5000.0],
            "Products_Below_Reorder": [0]}),
        "defect_analysis": {"by_type": pd.DataFrame({
            "Defect_Type": ["scratch"], "Total_Defects": [12],
            "Defect_Rate_pct": [1.5], "Total_Inspected": [800]})},
    }


def make_generator(fake, monkeypatch):
    import app.ai.reporting as reporting

    monkeypatch.setattr(reporting, "get_llm", lambda: fake)
    return reporting.AIReportGenerator()


# ------------------------------------------------------------- gate unit ----

def test_gate_good_snapshot():
    d = evaluate_quality(datasets=make_datasets(), kpis=make_kpis())
    assert d.status == GOOD, d.reason
    assert d.failures == []
    assert d.period.get("production_max", "").startswith("2026-09-30")


def test_gate_bad_nan_in_kpi():
    kpis = make_kpis()
    kpis["daily_production"].loc[0, "Achievement_Rate_pct"] = float("nan")
    d = evaluate_quality(datasets=make_datasets(), kpis=kpis)
    assert d.status == BAD
    assert any("non-finite" in f for f in d.failures)


def test_gate_bad_inf_in_kpi():
    kpis = make_kpis()
    kpis["oee"].loc[0, "OEE_pct"] = float("inf")
    d = evaluate_quality(datasets=make_datasets(), kpis=kpis)
    assert d.status == BAD


def test_gate_bad_missing_dataset():
    ds = make_datasets()
    del ds["machine"]
    d = evaluate_quality(datasets=ds, kpis=make_kpis())
    assert d.status == BAD
    assert any("missing required dataset" in f for f in d.failures)


def test_gate_bad_empty_dataset():
    ds = make_datasets()
    ds["quality"] = ds["quality"].iloc[0:0]
    d = evaluate_quality(datasets=ds, kpis=make_kpis())
    assert d.status == BAD


def test_gate_bad_missing_kpi_input():
    d = evaluate_quality(datasets=make_datasets(), kpis={"something_else": 1})
    assert d.status == BAD
    assert any("missing required KPI input" in f for f in d.failures)


def test_gate_bad_quarantine_rate():
    d = evaluate_quality(datasets=make_datasets(), kpis=make_kpis(),
                         quarantine={"passed": 10, "rejected": 90})
    assert d.status == BAD
    assert any("quarantine rate" in f for f in d.failures)


def test_gate_quarantine_normal_rate_is_good():
    d = evaluate_quality(datasets=make_datasets(), kpis=make_kpis(),
                         quarantine={"passed": 990, "rejected": 10})
    assert d.status == GOOD


def test_gate_unknown_on_evaluate_error_never_raises():
    # dict(object()) raises TypeError inside the gate -> UNKNOWN, fail closed.
    d = evaluate_quality(datasets=object(), kpis=make_kpis())
    assert d.status == UNKNOWN
    assert "quality evaluation error" in d.reason


# ---------------------------------------------------------- report paths ----

def test_good_quality_llm_called_once_real_model(monkeypatch):
    fake = FakeLLM(payload={"title": "Daily report", "summary": "s"})
    gen = make_generator(fake, monkeypatch)
    out = gen.generate_report(make_kpis(), [], make_datasets())
    assert fake.calls == 1
    assert out["status"] == "OK"
    assert out["generation_mode"] == "REAL_MODEL"
    assert out["quality"]["status"] == GOOD
    assert out["evidence"]["snapshot_id"].startswith("snap-")
    assert out["provenance"] == out["evidence"]["source_ids"]


def test_fallback_mode_is_honest_not_real_model(monkeypatch):
    fake = FakeLLM(available=False)
    gen = make_generator(fake, monkeypatch)
    out = gen.generate_report(make_kpis(), [], make_datasets())
    assert fake.calls == 0
    assert out["generation_mode"] == "FALLBACK"
    assert out["quality"]["status"] == GOOD
    assert out["evidence"]["snapshot_id"]


def test_bad_nan_quality_blocks_llm(monkeypatch):
    fake = FakeLLM()
    gen = make_generator(fake, monkeypatch)
    kpis = make_kpis()
    kpis["daily_production"].loc[0, "Achievement_Rate_pct"] = float("nan")
    out = gen.generate_report(kpis, [], make_datasets())
    assert fake.calls == 0, "LLM invoked on BAD quality"
    assert out["status"] == "BLOCKED"
    assert out["generation_mode"] == "NOT_RUN"
    assert out["evidence"] is None
    assert out["quality"]["status"] == BAD


def test_bad_missing_dataset_blocks_llm(monkeypatch):
    fake = FakeLLM()
    gen = make_generator(fake, monkeypatch)
    ds = make_datasets()
    del ds["production"]
    out = gen.generate_report(make_kpis(), [], ds)
    assert fake.calls == 0
    assert out["status"] == "BLOCKED"


def test_bad_quarantine_summary_blocks_llm(monkeypatch):
    fake = FakeLLM()
    gen = make_generator(fake, monkeypatch)
    out = gen.generate_report(make_kpis(), [], make_datasets(),
                              quarantine={"passed": 1, "rejected": 99})
    assert fake.calls == 0
    assert out["status"] == "BLOCKED"
    assert out["quality"]["status"] == BAD


def test_unknown_gate_error_blocks_llm(monkeypatch):
    fake = FakeLLM()
    gen = make_generator(fake, monkeypatch)
    out = gen.generate_report(make_kpis(), [], object())
    assert fake.calls == 0
    assert out["status"] == "BLOCKED"
    assert out["quality"]["status"] == UNKNOWN


def test_llm_cannot_override_quality_or_status(monkeypatch):
    fake = FakeLLM(payload={
        "title": "HACK", "quality": {"status": "GOOD"},
        "status": "BLOCKED", "generation_mode": "REAL_MODEL",
        "evidence": {"snapshot_id": "snap-forged"},
    })
    gen = make_generator(fake, monkeypatch)
    out = gen.generate_report(make_kpis(), [], make_datasets())
    assert out["quality"]["status"] == GOOD  # gate decision, not model's dict
    assert out["status"] == "OK"
    assert out["evidence"]["snapshot_id"] != "snap-forged"
    assert out["generation_mode"] == "REAL_MODEL"  # set by this code, verified by calls


def test_llm_fabricated_provenance_rejected(monkeypatch):
    fake = FakeLLM(payload={"title": "T",
                            "provenance": ["ghost:external-source"]})
    gen = make_generator(fake, monkeypatch)
    out = gen.generate_report(make_kpis(), [], make_datasets())
    assert "ghost:external-source" not in out["provenance"]
    assert out["provenance_rejected"] == 1
    assert set(out["provenance"]) == set(out["evidence"]["source_ids"])


def test_evidence_snapshot_deterministic(monkeypatch):
    from app.ai.reporting import extract_kpi_evidence

    ds, kpis = make_datasets(), make_kpis()
    d = evaluate_quality(datasets=ds, kpis=kpis)
    e1 = extract_kpi_evidence(kpis, ds, d)
    e2 = extract_kpi_evidence(kpis, ds, d)
    assert e1["snapshot_id"] == e2["snapshot_id"]
    fake = FakeLLM()
    gen = make_generator(fake, monkeypatch)
    out = gen.generate_report(kpis, [], ds)
    assert out["evidence"]["snapshot_id"] == e1["snapshot_id"]


def test_validate_provenance_membership():
    from app.ai.reporting import extract_kpi_evidence, validate_provenance

    ds, kpis = make_datasets(), make_kpis()
    d = evaluate_quality(datasets=ds, kpis=kpis)
    evidence = extract_kpi_evidence(kpis, ds, d)
    assert validate_provenance(evidence["source_ids"], evidence) == []
    assert validate_provenance(["nope:1", "kpi:oee"], evidence) == ["nope:1"]
    assert validate_provenance("not-a-list", evidence) == ["<provenance not a list>"]
