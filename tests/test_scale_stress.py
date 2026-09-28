"""FDA-013: Huge-input and Scale Stress Test.

Verifies that the ETL pipeline can handle 50,000+ rows without excessive
memory consumption (< 200 MB) or runaway latency (< 10 seconds).
"""

from __future__ import annotations

import sys
import time
import tracemalloc
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pd = pytest.importorskip("pandas", reason="Scale test requires pandas")
from app.etl.pipeline import clean_dataframe  # noqa: E402


def test_huge_input_scale_and_memory_safety():
    """FDA-013: Run clean_dataframe on 50,000 synthetic production rows."""
    n_rows = 50000

    # Build synthetic 50,000 rows dataset
    dates = ["2026-01-01"] * (n_rows // 2) + ["2026-01-02"] * (n_rows // 2)
    data = {
        "Date": dates,
        "Target_Qty": [100.0] * n_rows,
        "Actual_Qty": [95.0] * n_rows,
        "Good_Qty": [90.0] * n_rows,
        "Reject_Qty": [5.0] * n_rows,
        "Machine_ID": [f"M-{i % 20}" for i in range(n_rows)],
        "Cycle_Time_sec": [12.5] * n_rows,
    }
    # Introduce some duplicates, negative values, and nulls
    data["Target_Qty"][10] = -50.0
    data["Actual_Qty"][20] = None

    df_large = pd.DataFrame(data)
    assert len(df_large) == n_rows

    tracemalloc.start()
    t0 = time.perf_counter()

    cleaned = clean_dataframe(df_large, "production")

    elapsed_sec = time.perf_counter() - t0
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak_mem / (1024 * 1024)

    # Invariants for FDA-013:
    # 1. Pipeline finishes under 10 seconds for 50k rows
    assert elapsed_sec < 10.0, f"Scale test exceeded time limit: {elapsed_sec:.2f}s"

    # 2. Peak memory delta stays under 200 MB
    assert peak_mb < 200.0, f"Memory consumption exceeded safe threshold: {peak_mb:.2f} MB"

    # 3. Data integrity holds
    assert len(cleaned) <= n_rows
    assert (cleaned["Target_Qty"] >= 0).all()
    assert (cleaned["Actual_Qty"] >= 0).all()
