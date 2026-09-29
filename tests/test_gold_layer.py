"""
Test Gold layer — bảng curated từ silver.

Nguyên tắc được bảo vệ:
    * Gold KHÔNG đọc raw
    * Thiếu cột bắt buộc → raise (không tạo bảng rỗng im lặng)
    * Idempotent: chạy lại cho kết quả giống hệt
    * Deterministic: thứ tự dòng ổn định
    * Không mất dữ liệu âm thầm
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.etl.gold import (
    GOLD_DATASETS,
    GoldContractError,
    build_gold,
    build_inventory_snapshot,
    build_machine_health,
    build_oee_daily,
    build_quality_daily,
    export_gold,
)


@pytest.fixture
def production() -> pd.DataFrame:
    return pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-01", "2026-01-02"],
        "Line": ["L1", "L1", "L2"],
        "Shift": ["A", "B", "A"],
        "Product": ["P1", "P1", "P2"],
        "Machine_ID": ["M1", "M2", "M3"],
        "Worker_ID": ["W1", "W2", "W1"],
        "Target_Qty": [100, 100, 50],
        "Actual_Qty": [90, 80, 60],
        "Good_Qty": [88, 76, 55],
        "Reject_Qty": [2, 4, 5],
        "Cycle_Time_sec": [12.0, 14.0, 11.0],
    })


@pytest.fixture
def quality() -> pd.DataFrame:
    return pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "Product": ["P1", "P2"],
        "Line": ["L1", "L2"],
        "Defect_Type": ["Scratch", "Crack"],
        "Defect_Count": [3, 2],
        "Inspected_Qty": [100, 50],
        "Severity": ["Minor", "Major"],
        "Inspector_ID": ["I1", "I2"],
    })


@pytest.fixture
def inventory() -> pd.DataFrame:
    return pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02", "2026-01-02"],
        "Product": ["P1", "P2", "P3"],
        "Stock_Qty": [50, 5, 0],
        "Reorder_Point": [20, 10, 5],
        "Max_Capacity": [100, 100, 100],
        "Unit_Price": [10.0, 20.0, 30.0],
        "Supplier": ["S1", "S2", "S3"],
    })


@pytest.fixture
def machine() -> pd.DataFrame:
    return pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-01"],
        "Machine_ID": ["M1", "M2"],
        "Status": ["RUN", "DOWN"],
        "Temperature_C": [60.0, 85.0],
        "Vibration_mm": [2.0, 5.0],
        "Downtime_min": [0, 30],
        "Line": ["L1", "L2"],
    })


@pytest.fixture
def silver(production, quality, inventory, machine) -> dict:
    return {"production": production, "quality": quality,
            "inventory": inventory, "machine": machine}
# Schema + cấu trúc
# --------------------------------------------------------------------------
def test_build_gold_returns_all_four(silver):
    gold = build_gold(silver)
    assert set(gold) == set(GOLD_DATASETS)
    assert all(len(df) > 0 for df in gold.values()), "không dataset nào được phép rỗng"


def test_gold_schemas_are_deterministic_across_runs(silver):
    """Cùng input → cùng tên cột, cùng thứ tự cột."""
    a, b = build_gold(silver), build_gold(silver)
    for name in GOLD_DATASETS:
        assert list(a[name].columns) == list(b[name].columns), name


def test_gold_does_not_read_raw(silver):
    """Gold chỉ nhận frame đã clean. Thiếu dataset → raise, không đọc data/raw."""
    with pytest.raises(GoldContractError, match="silver"):
        build_gold({"production": silver["production"]})


@pytest.mark.parametrize("dataset,required", [
    ("production", "Good_Qty"),
    ("quality", "Severity"),
    ("inventory", "Reorder_Point"),
    ("machine", "Vibration_mm"),
])
def test_missing_required_column_raises_not_silently(silver, dataset, required):
    """Thiếu cột bắt buộc → raise. KHÔNG tạo bảng rỗng im lặng."""
    broken = {k: v.copy() for k, v in silver.items()}
    broken[dataset] = broken[dataset].drop(columns=[required])
    with pytest.raises(GoldContractError, match=required):
        build_gold(broken)


# --------------------------------------------------------------------------
# Aggregation correctness
# --------------------------------------------------------------------------
def test_oee_daily_aggregation_is_correct(production):
    out = build_oee_daily(production)
    first = out[out["Date"] == "2026-01-01"].iloc[0]
    assert first["Total_Target"] == 200
    assert first["Total_Actual"] == 170
    assert first["Total_Good"] == 164
    assert first["Total_Reject"] == 6
    assert first["Machine_Count"] == 2
    assert first["Quality_pct"] == pytest.approx(96.47, abs=0.01)     # 164/170
    assert first["Performance_pct"] == pytest.approx(85.0, abs=0.01)  # 170/200


def test_oee_daily_sorted_by_date(production):
    out = build_oee_daily(production.sample(frac=1, random_state=7))
    assert out["Date"].is_monotonic_increasing


def test_quality_daily_severity_pivot_keeps_date_column(quality):
    """
    Regression: pivot_table().reset_index() đặt tên cột là "index" chứ không
    phải "Date" — nếu đổi prefix luôn thì cột join thành "Defects_Date" và merge hỏng.
    """
    out = build_quality_daily(quality)
    assert "Date" in out.columns
    assert not any(c.startswith("Defects_Date") for c in out.columns)
    assert "Defects_Minor" in out.columns and "Defects_Major" in out.columns
    assert out["Total_Defects"].sum() == 5
    assert (out["Pass_Rate_pct"] + out["Defect_Rate_pct"] - 100).abs().max() < 0.01


def test_inventory_snapshot_takes_latest_date_only(inventory):
    out = build_inventory_snapshot(inventory)
    assert out["Snapshot_Date"].nunique() == 1


# --------------------------------------------------------------------------
# Idempotency + determinism
# --------------------------------------------------------------------------
def test_gold_is_idempotent_same_input_same_output(silver):
    a, b = build_gold(silver), build_gold(silver)
    for name in GOLD_DATASETS:
        pd.testing.assert_frame_equal(a[name], b[name], check_like=False)


def test_gold_aggregation_order_independent(production):
    """Thứ tự dòng input không được ảnh hưởng output."""
    a = build_oee_daily(production)
    b = build_oee_daily(production.sample(frac=1, random_state=42))
    pd.testing.assert_frame_equal(a, b)


def test_export_gold_overwrites_not_appends(silver, tmp_path):
    gold = build_gold(silver)
    m1 = export_gold(gold, outdir=str(tmp_path))
    m2 = export_gold(gold, outdir=str(tmp_path))
    assert m2["total_rows"] == m1["total_rows"]
    reread = pd.read_parquet(tmp_path / "oee_daily.parquet")
    assert len(reread) == len(gold["oee_daily"])


def test_export_gold_manifest_is_machine_readable(silver, tmp_path):
    m = export_gold(build_gold(silver), outdir=str(tmp_path))
    assert set(m["datasets"]) == set(GOLD_DATASETS)
    for name, meta in m["datasets"].items():
        assert meta["rows"] > 0
        assert isinstance(meta["columns"], list) and meta["columns"]
        assert meta["parquet"].endswith(f"{name}.parquet")


# --------------------------------------------------------------------------
# No silent data loss
# --------------------------------------------------------------------------
def test_no_silent_row_loss_gold_covers_all_input_dates(silver):
    """Mỗi ngày có trong silver phải xuất hiện trong gold tương ứng."""
    for src, builder in [("production", build_oee_daily),
                        ("quality", build_quality_daily),
                        ("machine", build_machine_health)]:
        out = builder(silver[src])
        src_dates = set(pd.to_datetime(silver[src]["Date"]).dropna())
        out_dates = set(pd.to_datetime(out["Date"]))
        assert src_dates == out_dates, f"{src}: mất ngày {src_dates - out_dates}"


def test_totals_conserved_production_to_oee(production):
    """Tổng ở silver phải bằng tổng ở gold — không mất dòng."""
    out = build_oee_daily(production)
    assert out["Total_Actual"].sum() == production["Actual_Qty"].sum()
    assert out["Total_Good"].sum() == production["Good_Qty"].sum()

    assert pd.to_datetime(out["Snapshot_Date"].iloc[0]) == pd.Timestamp("2026-01-02")
    assert set(out["Product"]) == {"P2", "P3"}


def test_inventory_status_classification(inventory):
    out = build_inventory_snapshot(inventory).set_index("Product")
    assert out.loc["P3", "Stock_Status"] == "OUT_OF_STOCK"   # Stock_Qty 0
    assert out.loc["P2", "Stock_Status"] == "REORDER"        # 5 < reorder 10
    assert out.loc["P2", "Stock_Value"] == 100.0             # 5 * 20.0


def test_machine_health_thresholds_are_explicit(machine):
    out = build_machine_health(machine)
    # Temp 85 > 75 VÀ Vib 5.0 > 4.5 → 2 cảnh báo → CRITICAL
    assert out.iloc[0]["Warning_Count"] == 2
    assert out.iloc[0]["Health_Status"] == "CRITICAL"
    assert out.iloc[0]["Downtime_Machine_Count"] == 1


def test_machine_health_healthy_when_below_thresholds(machine):
    calm = machine.copy()
    calm["Temperature_C"] = [50.0, 51.0]
    calm["Vibration_mm"] = [1.0, 1.2]


# --------------------------------------------------------------------------
# Idempotency + determinism
# --------------------------------------------------------------------------
def test_gold_is_idempotent_same_input_same_output(silver):
    a, b = build_gold(silver), build_gold(silver)
    for name in GOLD_DATASETS:
        pd.testing.assert_frame_equal(a[name], b[name], check_like=False)


def test_gold_aggregation_order_independent(production):
    """Thứ tự dòng input không được ảnh hưởng output."""
    a = build_oee_daily(production)
    b = build_oee_daily(production.sample(frac=1, random_state=42))
    pd.testing.assert_frame_equal(a, b)


def test_export_gold_overwrites_not_appends(silver, tmp_path):
    gold = build_gold(silver)
    m1 = export_gold(gold, outdir=str(tmp_path))
    m2 = export_gold(gold, outdir=str(tmp_path))
    assert m2["total_rows"] == m1["total_rows"]
    reread = pd.read_parquet(tmp_path / "oee_daily.parquet")
    assert len(reread) == len(gold["oee_daily"])


def test_export_gold_manifest_is_machine_readable(silver, tmp_path):
    m = export_gold(build_gold(silver), outdir=str(tmp_path))
    assert set(m["datasets"]) == set(GOLD_DATASETS)
    for name, meta in m["datasets"].items():
        assert meta["rows"] > 0
        assert isinstance(meta["columns"], list) and meta["columns"]
        assert meta["parquet"].endswith(f"{name}.parquet")


# --------------------------------------------------------------------------
# No silent data loss
# --------------------------------------------------------------------------
def test_no_silent_row_loss_gold_covers_all_input_dates(silver):
    """Mỗi ngày có trong silver phải xuất hiện trong gold tương ứng."""
    for src, builder in [("production", build_oee_daily),
                        ("quality", build_quality_daily),
                        ("machine", build_machine_health)]:
        out = builder(silver[src])
        src_dates = set(pd.to_datetime(silver[src]["Date"]).dropna())
        out_dates = set(pd.to_datetime(out["Date"]))
        assert src_dates == out_dates, f"{src}: mất ngày {src_dates - out_dates}"


def test_totals_conserved_production_to_oee(production):
    """Tổng ở silver phải bằng tổng ở gold — không mất dòng."""
    out = build_oee_daily(production)
    assert out["Total_Actual"].sum() == production["Actual_Qty"].sum()
    assert out["Total_Good"].sum() == production["Good_Qty"].sum()
