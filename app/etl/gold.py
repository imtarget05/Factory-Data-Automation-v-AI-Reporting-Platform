"""
Gold layer — curated, business-ready datasets.

Medallion: Bronze/Raw → Silver (cleaned) → **Gold (curated)** → Mart.

Gold KHÔNG đọc ngược raw. Nó chỉ nhận frame đã qua `run_etl()` /
`load_and_clean_all()` (tức là silver), rồi aggregate thành bảng chủ đề
dùng được cho BI mà không cần join lại dữ liệu thô.

Bốn bảng gold:
    oee_daily / quality_daily / inventory_snapshot / machine_health

Nguyên tắc bất di bất dịch:
    * Idempotent — chạy lại cùng input cho cùng output (không append)
    * Deterministic — sort theo khóa nghiệp vụ, không phụ thuộc thứ tự dict
    * Không mất dữ liệu âm thầm — số dòng được ghi vào manifest
    * Fail loud — thiếu cột bắt buộc thì raise, không tạo bảng rỗng giả
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from app.utils.logging_config import get_logger

logger = get_logger("etl", "gold")

GOLD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "gold",
)

GOLD_DATASETS = (
    "oee_daily",
    "quality_daily",
    "inventory_snapshot",
    "machine_health",
)

# Cột bắt buộc mỗi frame đầu vào. Thiếu → raise (fail loud, không im lặng bỏ).
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "production": ("Date", "Line", "Machine_ID", "Target_Qty", "Actual_Qty",
                   "Good_Qty", "Reject_Qty", "Cycle_Time_sec"),
    "quality": ("Date", "Product", "Line", "Defect_Type", "Defect_Count",
                "Inspected_Qty", "Severity"),
    "inventory": ("Date", "Product", "Stock_Qty", "Reorder_Point",
                  "Max_Capacity", "Unit_Price", "Supplier"),
    "machine": ("Date", "Machine_ID", "Status", "Temperature_C",
                "Vibration_mm", "Downtime_min", "Line"),
}


class GoldContractError(ValueError):
    """Raised khi input thiếu cột bắt buộc — không bao giờ im lặng bỏ qua."""


def _require(datasets: dict, name: str) -> pd.DataFrame:
    """Lấy frame đã clean (silver) và kiểm tra cột bắt buộc."""
    if name not in datasets or datasets[name] is None:
        raise GoldContractError(
            f"thiếu dataset '{name}' — gold chỉ nhận dữ liệu đã qua silver, "
            f"không đọc ngược raw"
        )
    df = datasets[name]
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    missing = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
    if missing:
        raise GoldContractError(
            f"dataset '{name}' thiếu cột bắt buộc: {missing} — có: {list(df.columns)}"
        )
    return df


def _safe_div(num, den):
    """Chia có kiểm soát: mẫu 0 → NA thay vì làm méo chỉ số. Nhận Series hoặc scalar."""
    if isinstance(den, pd.Series):
        den_safe = den.replace(0, pd.NA)
    else:
        den_safe = den if den else pd.NA
    return (pd.Series(num) / den_safe).astype("Float64")


# --------------------------------------------------------------------------
# 1. oee_daily
# --------------------------------------------------------------------------
def build_oee_daily(production: pd.DataFrame) -> pd.DataFrame:
    """OEE = Availability × Performance × Quality, theo ngày."""
    df = _require({"production": production}, "production").copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    if df.empty:
        raise GoldContractError("production không có Date hợp lệ sau khi parse")

    shift_agg = ("Shift", "nunique") if "Shift" in df.columns else ("Machine_ID", "size")
    out = (
        df.groupby("Date", as_index=False)
        .agg(
            Total_Target=("Target_Qty", "sum"),
            Total_Actual=("Actual_Qty", "sum"),
            Total_Good=("Good_Qty", "sum"),
            Total_Reject=("Reject_Qty", "sum"),
            Avg_Cycle_Time_sec=("Cycle_Time_sec", "mean"),
            Machine_Count=("Machine_ID", "nunique"),
            Shift_Count=shift_agg,
        )
    )
    out["Performance_pct"] = (_safe_div(out["Total_Actual"], out["Total_Target"]) * 100).round(2)
    out["Quality_pct"] = (_safe_div(out["Total_Good"], out["Total_Actual"]) * 100).round(2)
    out["Availability_pct"] = 100.0
    out["OEE_pct"] = (
        _safe_div(out["Availability_pct"], 100)
        * _safe_div(out["Performance_pct"], 100)
        * _safe_div(out["Quality_pct"], 100) * 100
    ).round(2)
    return out.sort_values("Date").reset_index(drop=True)


# --------------------------------------------------------------------------
# 2. quality_daily
# --------------------------------------------------------------------------
def build_quality_daily(quality: pd.DataFrame) -> pd.DataFrame:
    """Tổng hợp defect theo ngày + theo mức độ nghiêm trọng."""
    df = _require({"quality": quality}, "quality").copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    if df.empty:
        raise GoldContractError("quality không có Date hợp lệ sau khi parse")

    out = (
        df.groupby("Date", as_index=False)
        .agg(
            Total_Defects=("Defect_Count", "sum"),
            Total_Inspected=("Inspected_Qty", "sum"),
            Defect_Type_Count=("Defect_Type", "nunique"),
            Product_Count=("Product", "nunique"),
            Line_Count=("Line", "nunique"),
        )
    )
    # Pivot cố định để schema ổn định giữa các lần chạy.
    # reset_index() tạo cột tên là "index" (không phải "Date") nên phải đặt lại tên
    # trước khi đổi prefix — nếu không, cột join sẽ thành "Defects_Date" và merge hỏng.
    sev = (df.pivot_table(index="Date", columns="Severity",
                          values="Defect_Count", aggfunc="sum", fill_value=0)
           .reset_index().rename(columns={"index": "Date"}))
    sev.columns = ["Date" if c == "Date" else f"Defects_{c}" for c in sev.columns]
    out = out.merge(sev, on="Date", how="left")
    out["Defect_Rate_pct"] = (
        _safe_div(out["Total_Defects"], out["Total_Inspected"]) * 100).round(2)
    out["Pass_Rate_pct"] = (100 - out["Defect_Rate_pct"]).round(2)
    return out.sort_values("Date").reset_index(drop=True)


# --------------------------------------------------------------------------
# 3. inventory_snapshot
# --------------------------------------------------------------------------
def build_inventory_snapshot(inventory: pd.DataFrame) -> pd.DataFrame:
    """Snapshot tồn kho tại thời điểm mới nhất — bảng current state."""
    df = _require({"inventory": inventory}, "inventory").copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    if df.empty:
        raise GoldContractError("inventory không có Date hợp lệ sau khi parse")

    latest = df["Date"].max()
    snap = df[df["Date"] == latest].sort_values("Product").reset_index(drop=True)
    snap["Snapshot_Date"] = latest
    snap["Stock_Value"] = (snap["Stock_Qty"] * snap["Unit_Price"]).round(2)
    snap["Below_Reorder_Point"] = snap["Stock_Qty"] < snap["Reorder_Point"]
    snap["Capacity_Used_pct"] = (
        _safe_div(snap["Stock_Qty"], snap["Max_Capacity"]) * 100).round(2)
    snap["Stock_Status"] = "OK"
    # Thứ tự phải từ nghiêm ngặt → nhẹ: OVER_CAPACITY trước, REORDER sau,
    # OUT_OF_STOCK cuối. Nếu đảo thì OUT_OF_STOCK bị REORDER đè mất, vì
    # Stock_Qty=0 luôn < Reorder_Point nên .loc[] chạy sau sẽ ghi đè.
    snap.loc[snap["Capacity_Used_pct"] > 90, "Stock_Status"] = "OVER_CAPACITY"
    snap.loc[snap["Below_Reorder_Point"], "Stock_Status"] = "REORDER"
    snap.loc[snap["Stock_Qty"] <= 0, "Stock_Status"] = "OUT_OF_STOCK"
    return snap


# --------------------------------------------------------------------------
# 4. machine_health
# --------------------------------------------------------------------------
# Ngưỡng tường minh để test được, không magic number ẩn trong code.
TEMP_WARN_C = 75.0
VIB_WARN_MM = 4.5


def build_machine_health(machine: pd.DataFrame) -> pd.DataFrame:
    """Sức khoẻ máy theo ngày, cảnh báo theo ngưỡng tường minh."""
    df = _require({"machine": machine}, "machine").copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    if df.empty:
        raise GoldContractError("machine không có Date hợp lệ sau khi parse")

    out = (
        df.groupby("Date", as_index=False)
        .agg(
            Machine_Count=("Machine_ID", "nunique"),
            Avg_Temperature_C=("Temperature_C", "mean"),
            Max_Temperature_C=("Temperature_C", "max"),
            Avg_Vibration_mm=("Vibration_mm", "mean"),
            Max_Vibration_mm=("Vibration_mm", "max"),
            Total_Downtime_min=("Downtime_min", "sum"),
            Downtime_Machine_Count=("Status", lambda s: int((s == "DOWN").sum())),
        )
    )
    # round() không nhận được tuple trong .agg(), nên làm sau khi aggregate.
    out["Avg_Temperature_C"] = out["Avg_Temperature_C"].round(2)
    out["Max_Temperature_C"] = out["Max_Temperature_C"].round(2)
    out["Avg_Vibration_mm"] = out["Avg_Vibration_mm"].round(3)
    out["Max_Vibration_mm"] = out["Max_Vibration_mm"].round(3)
    out["Warning_Count"] = 0
    out.loc[out["Max_Temperature_C"] > TEMP_WARN_C, "Warning_Count"] += 1
    out.loc[out["Max_Vibration_mm"] > VIB_WARN_MM, "Warning_Count"] += 1
    out["Health_Status"] = out["Warning_Count"].map(
        {0: "HEALTHY", 1: "WARN", 2: "CRITICAL"}).fillna("HEALTHY")
    return out.sort_values("Date").reset_index(drop=True)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_gold(datasets: dict) -> dict[str, pd.DataFrame]:
    """Dựng cả 4 bảng gold từ silver datasets. Thiếu input thì raise."""
    builders = {
        "oee_daily": lambda: build_oee_daily(datasets.get("production")),
        "quality_daily": lambda: build_quality_daily(datasets.get("quality")),
        "inventory_snapshot": lambda: build_inventory_snapshot(datasets.get("inventory")),
        "machine_health": lambda: build_machine_health(datasets.get("machine")),
    }
    gold: dict[str, pd.DataFrame] = {}
    for name, build in builders.items():
        try:
            gold[name] = build()
        except GoldContractError as exc:
            logger.warning("gold dataset %s failed: %s", name, exc)
            raise
    return gold


def export_gold(gold: dict[str, pd.DataFrame],
                outdir: str | None = None) -> dict[str, Any]:
    """
    Ghi gold ra parquet (snappy) + csv.

    Idempotent: ghi đè, không append. Chạy lại cùng input → cùng nội dung.
    """
    outdir = outdir or GOLD_DIR
    os.makedirs(outdir, exist_ok=True)
    manifest: dict[str, Any] = {"outdir": outdir, "datasets": {}}
    for name in GOLD_DATASETS:
        if name not in gold:
            continue
        df = gold[name]
        pq = os.path.join(outdir, f"{name}.parquet")
        csv = os.path.join(outdir, f"{name}.csv")
        df.to_parquet(pq, engine="pyarrow", compression="snappy", index=False)
        df.to_csv(csv, index=False)
        manifest["datasets"][name] = {
            "parquet": pq, "csv": csv,
            "rows": int(len(df)), "columns": list(df.columns),
        }
    manifest["total_rows"] = int(sum(len(g) for g in gold.values()))
    return manifest
