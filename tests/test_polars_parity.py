"""FDA-009: Pandas vs Polars ETL parity.

Verifies that for identical input raw data:
1. Row count after clean matches exactly between Pandas and Polars.
2. Deduplication count matches between Pandas and Polars.
3. Quantity clipping behavior (no negatives) matches between Pandas and Polars.
4. Downstream KPIs calculated from both engine outputs match within tolerance.

Contract: docs/qa/QA_ACCEPTANCE.md -> FDA-009.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pd = pytest.importorskip("pandas", reason="Pandas/Polars parity requires pandas")
pl = pytest.importorskip("polars", reason="Pandas/Polars parity requires polars")

from app.etl.pipeline import clean_dataframe  # noqa: E402
from app.etl.polars_etl import clean_polars  # noqa: E402
from app.etl.kpi_engine import (  # noqa: E402
    calculate_daily_production,
    calculate_inventory_kpi,
)


def test_fda_009_pandas_polars_synthetic_parity():
    """Verify parity on controlled edge-case dataset: duplicates, nulls, negative quantities."""
    records = [
        {"Date": "2026-01-01", "Machine_ID": "M-01", "Target_Qty": 100, "Actual_Qty": 90, "Good_Qty": 85, "Reject_Qty": 5},
        {"Date": "2026-01-01", "Machine_ID": "M-01", "Target_Qty": 100, "Actual_Qty": 90, "Good_Qty": 85, "Reject_Qty": 5},  # duplicate
        {"Date": "2026-01-02", "Machine_ID": "M-02", "Target_Qty": 200, "Actual_Qty": 190, "Good_Qty": 180, "Reject_Qty": 10},
        {"Date": "2026-01-03", "Machine_ID": "M-01", "Target_Qty": -10, "Actual_Qty": 50, "Good_Qty": 50, "Reject_Qty": 0},  # negative
    ]
    df_pd = pd.DataFrame(records)
    df_pl = pl.DataFrame(records)

    c_pd = clean_dataframe(df_pd, "production")
    c_pl = clean_polars(df_pl, "production")

    # Row counts must match exactly (both remove 1 duplicate -> 3 rows)
    assert len(c_pd) == c_pl.height == 3

    # Negative quantities clipped to 0 on both engines
    assert (c_pd["Target_Qty"] >= 0).all()
    assert (c_pl["Target_Qty"] >= 0).all()

    # Sum of target and actual must be identical
    assert c_pd["Target_Qty"].sum() == c_pl["Target_Qty"].sum()
    assert c_pd["Actual_Qty"].sum() == c_pl["Actual_Qty"].sum()
    assert c_pd["Good_Qty"].sum() == c_pl["Good_Qty"].sum()


@pytest.mark.parametrize("dataset_name", ["production", "quality", "inventory", "machine", "workers"])
def test_fda_009_pandas_polars_raw_files_parity(dataset_name):
    """Verify row count and key column aggregates match between pandas and polars on actual raw data."""
    raw_csv = REPO_ROOT / "data" / "raw" / f"{dataset_name}.csv"
    if not raw_csv.exists():
        pytest.skip(f"Raw file {raw_csv} not present")

    df_pd = pd.read_csv(raw_csv)
    df_pl = pl.read_csv(raw_csv)

    c_pd = clean_dataframe(df_pd, dataset_name)
    c_pl = clean_polars(df_pl, dataset_name)

    # 1. Height must match exactly
    assert len(c_pd) == c_pl.height, f"Row count mismatch on {dataset_name}: PD={len(c_pd)}, PL={c_pl.height}"

    # 2. Check numeric column sum parity
    for col in ["Target_Qty", "Actual_Qty", "Good_Qty", "Reject_Qty", "Stock_Qty"]:
        if col in c_pd.columns and col in c_pl.columns:
            sum_pd = float(c_pd[col].sum())
            sum_pl = float(c_pl[col].sum())
            assert abs(sum_pd - sum_pl) < 1e-4, f"Sum mismatch on {dataset_name}.{col}: PD={sum_pd}, PL={sum_pl}"


def test_fda_009_downstream_kpi_parity():
    """Verify KPI calculation yields identical metrics whether feed is cleaned via Pandas or Polars."""
    prod_csv = REPO_ROOT / "data" / "raw" / "production.csv"
    inv_csv = REPO_ROOT / "data" / "raw" / "inventory.csv"
    if not prod_csv.exists() or not inv_csv.exists():
        pytest.skip("Required raw CSVs not present")

    # Production KPIs
    c_pd_prod = clean_dataframe(pd.read_csv(prod_csv), "production")
    c_pl_prod = clean_polars(pl.read_csv(prod_csv), "production").to_pandas()

    kpi_pd = calculate_daily_production(c_pd_prod)
    kpi_pl = calculate_daily_production(c_pl_prod)
    assert len(kpi_pd) == len(kpi_pl)
    assert abs(kpi_pd["Total_Actual"].sum() - kpi_pl["Total_Actual"].sum()) < 1e-4
    assert abs(kpi_pd["Achievement_Rate_pct"].mean() - kpi_pl["Achievement_Rate_pct"].mean()) < 1e-4

    # Inventory KPIs
    c_pd_inv = clean_dataframe(pd.read_csv(inv_csv), "inventory")
    c_pl_inv = clean_polars(pl.read_csv(inv_csv), "inventory").to_pandas()

    kpi_inv_pd = calculate_inventory_kpi(c_pd_inv)
    kpi_inv_pl = calculate_inventory_kpi(c_pl_inv)
    assert len(kpi_inv_pd) == len(kpi_inv_pl)
    assert abs(kpi_inv_pd["Total_Stock"].sum() - kpi_inv_pl["Total_Stock"].sum()) < 1e-4
    assert abs(kpi_inv_pd["Stock_Value"].sum() - kpi_inv_pl["Stock_Value"].sum()) < 1e-4


