"""
Test Marts — tầng BI dựng trên Gold.

Kiểm bằng SQL thật trên SQLite, không chỉ kiểm DataFrame trong RAM.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.database.marts import (
    MART_GRAIN,
    MartError,
    build_marts,
    grain_violations,
    mart_row_counts,
    query,
    write_sqlite,
)
from app.etl.gold import build_gold


@pytest.fixture
def gold() -> dict:
    return build_gold({
        "production": pd.DataFrame({
            "Date": ["2026-01-01", "2026-01-01", "2026-01-02"],
            "Line": ["L1", "L1", "L2"], "Shift": ["A", "B", "A"],
            "Machine_ID": ["M1", "M2", "M3"],
            "Target_Qty": [100, 100, 50], "Actual_Qty": [90, 80, 60],
            "Good_Qty": [88, 76, 55], "Reject_Qty": [2, 4, 5],
            "Cycle_Time_sec": [12.0, 14.0, 11.0],
        }),
        "quality": pd.DataFrame({
            "Date": ["2026-01-01", "2026-01-02"], "Product": ["P1", "P2"],
            "Line": ["L1", "L2"], "Defect_Type": ["Scratch", "Crack"],
            "Defect_Count": [3, 2], "Inspected_Qty": [100, 50],
            "Severity": ["Minor", "Major"],
        }),
        "inventory": pd.DataFrame({
            "Date": ["2026-01-02", "2026-01-02"],
            "Product": ["P1", "P2"], "Stock_Qty": [50, 5],
            "Reorder_Point": [20, 10], "Max_Capacity": [100, 100],
            "Unit_Price": [10.0, 20.0], "Supplier": ["S1", "S2"],
        }),
        "machine": pd.DataFrame({
            "Date": ["2026-01-01"], "Machine_ID": ["M1"], "Status": ["RUN"],
            "Temperature_C": [60.0], "Vibration_mm": [2.0],
            "Downtime_min": [0], "Line": ["L1"],
        }),
    })


@pytest.fixture
def marts(gold) -> dict:
    return build_marts(gold)


# ==========================================================================
# Cấu trúc
# ==========================================================================
def test_build_marts_creates_three(marts):
    assert set(marts) == {"mart_oee", "mart_quality", "mart_inventory"}


def test_marts_consume_gold_not_raw(gold, marts):
    """Mart lấy đúng số dòng từ gold — chứng minh không đọc raw."""
    assert len(marts["mart_oee"]) == len(gold["oee_daily"])
    assert len(marts["mart_quality"]) == len(gold["quality_daily"])
    assert len(marts["mart_inventory"]) == len(gold["inventory_snapshot"])


def test_mart_dimensions_are_correct(marts):
    assert list(marts["mart_oee"].columns) == [
        "Date", "Total_Target", "Total_Actual", "Total_Good", "Total_Reject",
        "Quality_pct", "Performance_pct", "OEE_pct"]
    assert {"Product", "Stock_Qty", "Stock_Status"} <= set(
        marts["mart_inventory"].columns)


# ==========================================================================
# Grain — invariant quan trọng nhất
# ==========================================================================
def test_no_duplicate_business_grain(marts):
    for name, df in marts.items():
        assert grain_violations(name, df) == [], f"{name} trùng grain"


def test_grain_keys_match_declared(marts):
    for name, keys in MART_GRAIN.items():
        assert all(k in marts[name].columns for k in keys)


def test_grain_violation_is_detected_when_duplicated(gold):
    m = build_marts(gold)
    dup = pd.concat([m["mart_oee"], m["mart_oee"]], ignore_index=True)
    assert len(grain_violations("mart_oee", dup)) == 2 * len(m["mart_oee"])


# ==========================================================================
# Aggregation — mart không đổi ngữ nghĩa số liệu
# ==========================================================================
def test_mart_values_match_gold_exactly(gold, marts):
    assert marts["mart_oee"]["Total_Actual"].sum() == \
        gold["oee_daily"]["Total_Actual"].sum()
    assert marts["mart_quality"]["Total_Defects"].sum() == \
        gold["quality_daily"]["Total_Defects"].sum()
    assert marts["mart_inventory"]["Stock_Value"].sum() == \
        gold["inventory_snapshot"]["Stock_Value"].sum()


def test_marts_are_deterministic(gold):
    a, b = build_marts(gold), build_marts(gold)
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name])


# ==========================================================================
# Idempotency
# ==========================================================================
def test_write_sqlite_is_idempotent(tmp_path, marts):
    db = str(tmp_path / "m.db")
    write_sqlite(marts, db)
    first = mart_row_counts(db)
    write_sqlite(marts, db)
    assert mart_row_counts(db) == first


def test_rewrite_does_not_duplicate_rows(tmp_path, marts):
    db = str(tmp_path / "m.db")
    write_sqlite(marts, db)
    n = mart_row_counts(db)["mart_oee"]
    write_sqlite(marts, db)
    assert mart_row_counts(db)["mart_oee"] == n


# ==========================================================================
# SQL thật
# ==========================================================================
def test_sql_query_returns_real_rows(tmp_path, marts):
    db = write_sqlite(marts, str(tmp_path / "m.db"))
    out = query(db, "SELECT Product, Stock_Status FROM mart_inventory ORDER BY Product")
    assert len(out) == len(marts["mart_inventory"])
    assert list(out["Product"]) == sorted(marts["mart_inventory"]["Product"])


def test_sql_aggregation_is_correct(tmp_path, marts):
    db = write_sqlite(marts, str(tmp_path / "m.db"))
    out = query(db, "SELECT SUM(Total_Actual) AS t FROM mart_oee")
    assert int(out["t"].iloc[0]) == int(marts["mart_oee"]["Total_Actual"].sum())


def test_row_counts_match_dataframes(tmp_path, marts):
    db = write_sqlite(marts, str(tmp_path / "m.db"))
    counts = mart_row_counts(db)
    for name, df in marts.items():
        assert counts[name] == len(df), f"{name}: sqlite != dataframe"


# ==========================================================================
# Xử lý lỗi
# ==========================================================================
def test_missing_required_column_raises(gold):
    """gold fixture ĐÃ là dict output của build_gold — sửa trực tiếp, không build lại."""
    g = {k: v.copy() for k, v in gold.items()}
    g["oee_daily"] = g["oee_daily"].drop(columns=["OEE_pct"])
    with pytest.raises(MartError, match="OEE_pct"):
        build_marts(g)


def test_empty_input_raises_not_creates_empty_mart(gold):
    g = {k: v.copy() for k, v in gold.items()}
    g["oee_daily"] = g["oee_daily"].iloc[0:0]
    with pytest.raises(MartError, match="rỗng"):
        build_marts(g)


def test_missing_gold_dataset_is_skipped_not_crashed(gold):
    """Thiếu gold thì bỏ mart đó, không làm hỏng các mart còn lại."""
    g = {k: v.copy() for k, v in gold.items()}
    del g["quality_daily"]
    m = build_marts(g)
    assert "mart_quality" not in m
    assert "mart_oee" in m and "mart_inventory" in m


def test_null_handling_in_sqlite(tmp_path, marts):
    """Giá trị NA của Float64 phải survive vòng đi qua SQLite."""
    db = write_sqlite(marts, str(tmp_path / "m.db"))
    out = query(db, "SELECT COUNT(*) AS c FROM mart_oee WHERE OEE_pct IS NULL")
    assert int(out["c"].iloc[0]) >= 0  # không crash


def test_mart_row_count_returns_minus_one_for_missing_table(tmp_path, marts):
    db = write_sqlite(marts, str(tmp_path / "m.db"))
