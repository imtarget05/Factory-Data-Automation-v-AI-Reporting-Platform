"""Phase C mutation controls — prove the quality-boundary tests can fail.

XFAIL = MUTATION CAUGHT. These are NOT ordinary production passes: each test
applies ONE temporary mutation (reverted automatically by monkeypatch),
shows the mutation is visible, then records the expected test failure via
pytest.xfail. No mutated code is ever committed.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from test_ai_quality_gate import (  # noqa: E402
    FakeLLM,
    make_datasets,
    make_generator,
    make_kpis,
)

pd = pytest.importorskip("pandas")


def _xfail(msg: str) -> None:
    pytest.xfail(msg)


def test_m1_bad_quality_classified_good_detected(monkeypatch):
    """M1: gate always returns GOOD -> quality authorization test fails."""
    import app.ai.reporting as reporting
    from app.data_contracts.quality_gate import GOOD as _GOOD
    from app.data_contracts.quality_gate import QualityDecision

    fake = FakeLLM()
    gen = make_generator(fake, monkeypatch)
    monkeypatch.setattr(
        reporting,
        "evaluate_quality",
        lambda **kw: QualityDecision(status=_GOOD, reason="mutated-always-good"),
    )
    ds = make_datasets()
    del ds["production"]  # genuinely BAD input
    out = gen.generate_report(make_kpis(), [], ds)
    assert out["status"] != "BLOCKED"  # mutation visible: BAD data got a report
    assert fake.calls >= 1
    _xfail("M1 caught: BAD quality reclassified GOOD (quality-authorization test would FAIL)")


def test_m2_block_guard_neutered_detected(monkeypatch):
    """M2: GOOD constant neutered -> the `!= GOOD` block never fires -> LLM-zero test fails."""
    import app.ai.reporting as reporting

    fake = FakeLLM()
    gen = make_generator(fake, monkeypatch)
    monkeypatch.setattr(reporting, "GOOD", "BAD")  # decision.status("BAD") != "BAD" -> False
    ds = make_datasets()
    del ds["quality"]
    out = gen.generate_report(make_kpis(), [], ds)
    assert out["status"] == "OK"  # mutation visible: report generated on BAD
    assert fake.calls == 1
    _xfail("M2 caught: block guard removed (llm-call-zero test would FAIL)")


def test_m3_nan_through_trusted_evidence_detected(monkeypatch):
    """M3: finite check disabled -> NaN data is tolerated into the report.

    The evidence sanitizer coerces NaN to null, so the mutation's visible
    symptom is a report whose trusted KPI value silently degrades to null
    instead of the gate blocking the batch.
    """
    import app.data_contracts.quality_gate as qg

    fake = FakeLLM()
    gen = make_generator(fake, monkeypatch)
    monkeypatch.setattr(qg, "_finite_check", lambda kpis: (True, []))
    kpis = make_kpis()
    kpis["daily_production"].loc[0, "Achievement_Rate_pct"] = float("nan")
    out = gen.generate_report(kpis, [], make_datasets())
    assert out["status"] == "OK"  # mutation visible: gate let it through
    evidence = out["evidence"]
    assert evidence["kpis"]["daily_production"]["Achievement_Rate_pct"] is None
    assert fake.calls == 1
    _xfail("M3 caught: NaN tolerated into trusted evidence as null (quality/data test would FAIL)")


def test_m4_unauthorized_provenance_accepted_detected(monkeypatch):
    """M4: provenance validator neutered -> fabricated source id accepted."""
    import app.ai.reporting as reporting

    fake = FakeLLM(payload={"title": "T", "provenance": ["ghost:external"]})
    gen = make_generator(fake, monkeypatch)
    monkeypatch.setattr(reporting, "validate_provenance", lambda ids, ev: [])
    out = gen.generate_report(make_kpis(), [], make_datasets())
    assert "ghost:external" in out["provenance"]  # mutation visible
    _xfail("M4 caught: unauthorized provenance reference accepted (grounding test would FAIL)")
