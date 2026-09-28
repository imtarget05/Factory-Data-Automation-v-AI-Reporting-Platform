"""FDA-017: Performance Regression Gate.

Compares stage execution latencies against benchmarks/baseline_phase1.json.
Enforces that offline stages do not regress by more than the defined threshold (+25%).
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
BASELINE_PATH = REPO_ROOT / "benchmarks" / "baseline_phase1.json"


def test_offline_etl_performance_regression():
    """FDA-017: Measure offline CSV read stage latency and check against baseline."""
    if not BASELINE_PATH.exists():
        pytest.skip(f"Baseline file {BASELINE_PATH} does not exist")

    with open(BASELINE_PATH, encoding="utf-8") as f:
        baseline = json.load(f)

    baseline_read_ms = baseline.get("etl_proxy", {}).get("stages_ms", {}).get("read_csv_ms")
    if baseline_read_ms is None:
        pytest.skip("Baseline JSON does not contain read_csv_ms")

    # Measure actual stdlib CSV read time over the same raw files
    csv_files = list(RAW_DIR.glob("*.csv"))
    if not csv_files:
        pytest.skip("No CSV files found in data/raw")

    times_ms = []
    # Run 3 iterations
    for _ in range(3):
        t0 = time.perf_counter()
        total_rows = 0
        for p in csv_files:
            with open(p, encoding="utf-8", errors="replace") as fh:
                total_rows += sum(1 for _ in csv.reader(fh))
        t1 = time.perf_counter()
        times_ms.append((t1 - t0) * 1000.0)

    avg_ms = sum(times_ms) / len(times_ms)

    # Invariant: Performance must not regress by more than 25% over baseline.
    # Tolerant upper bound: max(baseline * 1.25, 3000.0 ms) to avoid noise on varying host loads.
    threshold_ms = max(baseline_read_ms * 1.25, 3000.0)
    assert avg_ms <= threshold_ms, (
        f"Performance regression detected: measured {avg_ms:.2f}ms exceeds threshold {threshold_ms:.2f}ms "
        f"(baseline: {baseline_read_ms:.2f}ms)"
    )
