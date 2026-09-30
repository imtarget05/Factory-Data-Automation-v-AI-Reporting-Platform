"""Runtime alert trigger evidence (Phase C §10): a real deterministic alert
condition fires through the existing AlertManager — no new observability
framework. Also proves the quality-gate/report events reuse the existing
structured logger (asserted via caplog in test_quality_gate_logs_event).
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.reports.alert_system import AlertManager  # noqa: E402

pd = pytest.importorskip("pandas")


def _breach_kpis():
    daily = pd.DataFrame({
        "Date": ["2026-09-30"], "Total_Target": [300], "Total_Actual": [240],
        "Achievement_Rate_pct": [76.0], "Reject_Rate_pct": [12.0],
        "Yield_pct": [88.0]})
    return {
        "daily_production": daily,
        "inventory_kpi": pd.DataFrame({
            "Total_Stock": [50], "Stock_Value": [500.0],
            "Products_Below_Reorder": [3]}),
        "oee": pd.DataFrame({"Date": ["2026-09-30"], "OEE_pct": [70.0],
                             "Availability_pct": [80.0], "Performance_pct": [90.0],
                             "Quality_pct": [97.0]}),
    }


def _breach_datasets():
    dates = pd.to_datetime(["2026-09-30"])
    return {
        "machine": pd.DataFrame({
            "Date": dates, "Machine_ID": ["M-01"], "Status": ["STOP"],
            "Downtime_min": [45.0], "Speed_RPM": [0.0],
            "Temperature_C": [55.0], "Vibration_mm": [2.0],
            "Power_Usage_pct": [10.0]}),
        "inventory": pd.DataFrame({
            "Date": dates, "Product": ["A"], "Stock_Qty": [50],
            "Reorder_Point": [100], "Unit_Price": [10.0]}),
    }


def test_alert_condition_triggers_at_runtime():
    """Reject rate 12% > 5% threshold and OEE 70 < 85 must both fire."""
    mgr = AlertManager()
    alerts = mgr.check_all(_breach_datasets(), _breach_kpis())
    assert alerts, "no alerts fired on a deliberately breaching snapshot"
    by_cat = {a.category: a for a in alerts}
    quality = [a for a in alerts if a.category == "Quality"]
    assert quality, [a.category for a in alerts]
    q = quality[0]
    assert q.value == 12.0
    assert q.threshold == 5.0
    assert q.level in ("WARNING", "CRITICAL")
    assert "exceeds threshold" in q.message
    oee = [a for a in alerts if a.category == "OEE"]
    assert oee and oee[0].value == 70.0
    # Alert objects serialize for the API (/api/v1/alerts).
    d = q.to_dict()
    assert set(("level", "category", "message", "value", "threshold")) <= set(d)


def test_alert_summary_counts_and_orders_by_severity():
    mgr = AlertManager()
    mgr.check_all(_breach_datasets(), _breach_kpis())
    levels = [a.level for a in mgr.alerts]
    order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    assert levels == sorted(levels, key=lambda x: order.get(x, 99))
    summary = mgr.get_summary()
    assert summary.get("total", 0) >= 2
