"""
Data marts — tầng trình bày cho BI, dựng trên Gold.

Medallion: raw -> silver -> gold -> **mart**.

Mart KHÔNG đọc raw. Mart chỉ đọc Gold. Nếu cần thêm bảng mart mới thì
bổ sung ở đây, không sửa pipeline đang chạy.

Mỗi mart có **business grain** rõ ràng, khai báo bằng hằng số
`MART_GRAIN` để test được — grain sai là lỗi kinh doanh, không phải lỗi kỹ thuật.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

import pandas as pd

from app.etl.gold import GoldContractError

MARTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "marts",
)
DB_NAME = "marts.db"

# Grain nghiệp vụ của từng mart. Dùng để assert không trùng dòng.
MART_GRAIN: dict[str, list[str]] = {
    "mart_oee": ["Date"],
    "mart_quality": ["Date"],
    "mart_inventory": ["Product"],
}

# Mart nào lấy từ gold dataset nào.
MART_SOURCE: dict[str, str] = {
    "mart_oee": "oee_daily",
    "mart_quality": "quality_daily",
    "mart_inventory": "inventory_snapshot",
}

# Cột phải có để coi là mart hợp lệ — thiếu thì raise, không tạo bảng rỗng.
MART_REQUIRED: dict[str, list[str]] = {
    "mart_oee": ["Date", "Total_Actual", "OEE_pct"],
    "mart_quality": ["Date", "Total_Defects", "Defect_Rate_pct"],
    "mart_inventory": ["Product", "Stock_Qty", "Stock_Status"],
}


class MartError(ValueError):
    """Mart không hợp lệ — thiếu cột, sai grain, hoặc input rỗng."""


def _validate(name: str, df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in MART_REQUIRED[name] if c not in df.columns]
    if missing:
        raise MartError(f"{name}: thiếu cột bắt buộc {missing} — có {list(df.columns)}")
    if df.empty:
        raise MartError(f"{name}: input rỗng — không tạo mart rỗng để che lỗi upstream")
    return df


def _project(name: str, df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Chiếu cột theo danh sách cho trước.

    Validate TRƯỚC khi select — nếu không, pandas ném KeyError thô và che mất
    thông báo "thiếu cột bắt buộc" dễ hiểu hơn.
    """
    _validate(name, df)
    return df[[c for c in cols if c in df.columns]].copy()


def build_marts(gold: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """
    Dựng 3 mart từ gold.

    Mart chỉ đổi tên/shape cho phù hợp BI, KHÔNG đổi ngữ nghĩa số liệu —
    mọi phép tính đã xong ở tầng gold.
    """
    marts: dict[str, pd.DataFrame] = {}

    oee = gold.get("oee_daily")
    if oee is not None:
        m = _project("mart_oee", oee, [
            "Date", "Total_Target", "Total_Actual", "Total_Good", "Total_Reject",
            "Quality_pct", "Performance_pct", "OEE_pct"])
        marts["mart_oee"] = m.sort_values("Date").reset_index(drop=True)

    qual = gold.get("quality_daily")
    if qual is not None:
        m = _project("mart_quality", qual, [
            "Date", "Total_Defects", "Total_Inspected", "Defect_Rate_pct",
            "Pass_Rate_pct", "Defect_Type_Count", "Product_Count"])
        marts["mart_quality"] = m.sort_values("Date").reset_index(drop=True)

    inv = gold.get("inventory_snapshot")
    if inv is not None:
        m = _project("mart_inventory", inv, [
            "Product", "Stock_Qty", "Reorder_Point", "Stock_Value",
            "Stock_Status", "Snapshot_Date"])
        marts["mart_inventory"] = m.sort_values("Product").reset_index(drop=True)

    return marts


def grain_violations(name: str, df: pd.DataFrame) -> list:
    """Các hàng vi phạm grain (trùng khóa). Rỗng = grain đúng."""
    keys = MART_GRAIN[name]
    dup = df[df.duplicated(subset=keys, keep=False)]
    return dup[keys].to_dict("records")


def write_sqlite(marts: dict[str, pd.DataFrame], db_path: str | None = None) -> str:
    """
    Ghi mart vào SQLite để query thật.

    Idempotent: DROP trước CREATE, nên chạy lại cho cùng kết quả.
    """
    db_path = db_path or os.path.join(MARTS_DIR, DB_NAME)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as con:
        for name, df in marts.items():
            con.execute(f'DROP TABLE IF EXISTS "{name}"')
            df.to_sql(name, con, index=False)
    return db_path


def query(db_path: str, sql: str) -> pd.DataFrame:
    """Chạy SQL thật trên mart — dùng cho test và cho dashboard."""
    with sqlite3.connect(db_path) as con:
        return pd.read_sql_query(sql, con)


def mart_row_counts(db_path: str) -> dict[str, int]:
    out: dict[str, int] = {}
    with sqlite3.connect(db_path) as con:
        for name in MART_SOURCE:
            try:
                out[name] = int(
                    con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
            except sqlite3.OperationalError:
                out[name] = -1  # bảng không tồn tại
    return out


def kpi_summary(db_path: str) -> dict:
    """
    Doc mart bang SQL that va tra ve chi so dashboard.

    Day la bang chung mart **tieu thu duoc**: BI chi can ham nay, khong can
    cham vao gold/raw.
    """
    with sqlite3.connect(db_path) as con:
        def scalar(sql: str, default=None):
            row = con.execute(sql).fetchone()
            return row[0] if row and row[0] is not None else default

        return {
            "total_actual_qty": scalar("SELECT SUM(Total_Actual) FROM mart_oee", 0),
            "total_reject_qty": scalar("SELECT SUM(Total_Reject) FROM mart_oee", 0),
            "avg_oee_pct": scalar("SELECT ROUND(AVG(OEE_pct), 2) FROM mart_oee"),
            "days_with_data": scalar("SELECT COUNT(*) FROM mart_oee", 0),
            "total_defects": scalar("SELECT SUM(Total_Defects) FROM mart_quality", 0),
            "defect_rate_pct": scalar(
                "SELECT ROUND(AVG(Defect_Rate_pct), 2) FROM mart_quality"),
            "skus_not_ok": scalar(
                "SELECT COUNT(*) FROM mart_inventory WHERE Stock_Status <> 'OK'", 0),
            "inventory_value": scalar(
                "SELECT ROUND(SUM(Stock_Value), 2) FROM mart_inventory", 0),
        }


def build_all_marts(silver: dict, db_path: str | None = None) -> tuple:
    """
    Silver -> Gold -> Mart -> SQLite trong mot lenh.

    Tra ve (db_path, marts) de caller kiem duoc ca hai ve.
    """
    from app.etl.gold import build_gold  # import cuc bo tranh vong lap

    marts = build_marts(build_gold(silver))
    return write_sqlite(marts, db_path), marts


def register_marts_in_catalog(catalog, lineage=None, transform: str = "materialize") -> None:
    """
    Khai bao 3 mart trong catalog va noi lineage gold -> mart.

    Nho do catalog phan anh dung nhung gi thuc su ton tai: mart duoc khai
    bao khi mart da implement, khong som hon.
    """
    for name, source in MART_SOURCE.items():
        if catalog.has(name):
            continue
        catalog.register(
            name=name,
            description=f"BI mart: {name}",
            owner="manufacturing-data",
            zone="MART",
            source=[source],
            version="1.0.0",
            consumers=[],
            freshness_sla_hours=48,
        )
    if lineage is not None:
        for name, source in MART_SOURCE.items():
            lineage.add_edge(source, name, transform, run_id="mart-build")
