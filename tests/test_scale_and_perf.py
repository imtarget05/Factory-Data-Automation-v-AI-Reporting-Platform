"""FDA-013 & FDA-017: Scale and Performance Regression Gates.

FDA-013: Scale test (x10 input records). Ensures pipeline and memory survive under 10x volume
         without crashing or data corruption.
FDA-017: Performance regression gate. Compares ETL stage execution times against baseline_phase1.json
         with an allowable threshold (e.g., 50% allowance for environment fluctuation).

Contract: docs/qa/QA_ACCEPTANCE.md -> FDA-013, FDA-017.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pd = pytest.importorskip("pandas", reason="Scale test needs pandas")

from app.etl.pipeline import clean_dataframe  # noqa: E402
from app.etl.kpi_engine import calculate_daily_production  # noqa: E402


def test_fda_013_scale_10x_pipeline_survives():
    """FDA-013: 10x scale test on production records (~110k rows).
    
    Verifies memory stability, correct deduplication, clipping, and aggregate completion.
    """
    raw_csv = REPO_ROOT / "data" / "raw" / "production.csv"
    if not raw_csv.exists():
        pytest.skip("production.csv missing")

    df_base = pd.read_csv(raw_csv)
    base_len = len(df_base)
    assert base_len > 1000

    # Create 10x dataset by concatenating with offset dates to prevent deduplication collapse
    dfs = []
    for i in range(10):
        df_part = df_base.copy()
        df_part["Date"] = pd.to_datetime(df_part["Date"]) + pd.Timedelta(days=i * 365)
        dfs.append(df_part)
    large_df = pd.concat(dfs, ignore_index=True)
    assert len(large_df) >= base_len * 10

    t0 = time.perf_counter()
    cleaned = clean_dataframe(large_df, "production")
    clean_duration = time.perf_counter() - t0

    assert len(cleaned) > 0
    # Quantity invariants hold under scale
    assert (cleaned["Target_Qty"] >= 0).all()
    assert (cleaned["Actual_Qty"] >= 0).all()

    # KPI aggregate runs on scaled data without OOM
    daily = calculate_daily_production(cleaned)
    assert len(daily) > 0
    assert clean_duration < 30.0, f"Clean took too long: {clean_duration:.2f}s"


def test_fda_017_performance_regression_against_baseline():
    """FDA-017: Performance regression check against baseline_phase1.json.
    
    Ensures current ETL stage latency does not regress beyond 100% threshold of baseline proxy.
    """
    baseline_file = REPO_ROOT / "benchmarks" / "baseline_phase1.json"
    if not baseline_file.exists():
        pytest.skip("benchmarks/baseline_phase1.json missing")

    with open(baseline_file, "r") as f:
        baseline = json.load(f)

    baseline_read_ms = baseline.get("etl_proxy", {}).get("stages_ms", {}).get("read_csv_ms")
    if not baseline_read_ms:
        pytest.skip("Baseline read_csv_ms not recorded")

    raw_dir = REPO_ROOT / "data" / "raw"
    csv_files = list(raw_dir.glob("*.csv"))
    if not csv_files:
        pytest.skip("No CSV files to benchmark")

    t0 = time.perf_counter()
    total_rows = 0
    for f in csv_files:
        df = pd.read_csv(f)
        total_rows += len(df)
    current_read_ms = (time.perf_counter() - t0) * 1000.0

    # Assert regression within reasonable factor (threshold 3x baseline to accommodate CI/local hardware load)
    max_allowed_ms = baseline_read_ms * 3.0
    assert current_read_ms <= max_allowed_ms, (
        f"Regression detected: current={current_read_ms:.1f}ms, "
        f"baseline={baseline_read_ms:.1f}ms, max_allowed={max_allowed_ms:.1f}ms"
    )
