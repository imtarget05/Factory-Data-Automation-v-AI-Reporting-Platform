"""Shared pytest fixtures.

`data/raw/` is gitignored, so a fresh clone has no input data. Without a seed
the two discovery tests in `tests/test_etl.py` can only fail. This fixture
makes `pytest` self-sufficient on a bare clone: it runs the committed
deterministic generator once per session, and only when the data is actually
missing, so it never slows down or changes the behaviour of an already-seeded
run.

Offline fallback: the full generator needs numpy/pandas/faker (CI installs
them). When those are absent (offline fresh clone), a stdlib-only mini-seeder
writes schema-compatible CSVs so discovery + stdlib invariant tests still run.
pandas-dependent tests self-skip via `pytest.importorskip` in their modules.
"""

import csv
import glob
import os
import random
import sys
from datetime import date, timedelta

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.utils.config import DATA_RAW_DIR  # noqa: E402

_FALLBACK_SEED = 42
_FALLBACK_DAYS = 3


def _fallback_seed() -> None:
    """Write minimal schema-compatible CSVs with stdlib only (offline clone)."""
    rng = random.Random(_FALLBACK_SEED)
    lines = ["L1", "L2"]
    products = ["SKU-A", "SKU-B"]
    machines = ["M-01", "M-02"]
    workers = ["W-001", "W-002", "W-003"]
    shifts = ["Shift-1", "Shift-2"]
    base = date(2026, 1, 5)
    dates = [(base + timedelta(days=i)).isoformat() for i in range(_FALLBACK_DAYS)]

    def write(name, header, rows):
        with open(os.path.join(DATA_RAW_DIR, name), "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)

    os.makedirs(DATA_RAW_DIR, exist_ok=True)
    prod = []
    for d in dates:
        for i in range(10):
            target = 400 + rng.randint(-50, 50)
            actual = target - rng.randint(0, 30)
            good = actual - rng.randint(0, 8)
            prod.append(
                [
                    d,
                    rng.choice(lines),
                    rng.choice(shifts),
                    rng.choice(products),
                    rng.choice(machines),
                    rng.choice(workers),
                    target,
                    actual,
                    good,
                    actual - good,
                    round(rng.uniform(30, 120), 1),
                    f"{d}T07:00:00",
                ]
            )
    prod[0][6] = -prod[0][6]  # one negative target mirrors the cleaning contract
    write(
        "production.csv",
        [
            "Date",
            "Line",
            "Shift",
            "Product",
            "Machine_ID",
            "Worker_ID",
            "Target_Qty",
            "Actual_Qty",
            "Good_Qty",
            "Reject_Qty",
            "Cycle_Time_sec",
            "Created_At",
        ],
        prod,
    )

    qual = [
        [
            d,
            rng.choice(products),
            rng.choice(lines),
            "Scratch",
            rng.randint(1, 9),
            200,
            "Minor",
            "W-001",
            f"{d}T08:00:00",
        ]
        for d in dates
        for _ in range(6)
    ]
    write(
        "quality.csv",
        [
            "Date",
            "Product",
            "Line",
            "Defect_Type",
            "Defect_Count",
            "Inspected_Qty",
            "Severity",
            "Inspector_ID",
            "Created_At",
        ],
        qual,
    )

    inv = [
        [d, p, 500 + rng.randint(-50, 50), 15, 20, 150, 2000, 25.5, "ACME", f"{d}T08:00:00"]
        for d in dates
        for p in products
    ]
    inv[0][2] = -50
    write(
        "inventory.csv",
        [
            "Date",
            "Product",
            "Stock_Qty",
            "Incoming_Qty",
            "Outgoing_Qty",
            "Reorder_Point",
            "Max_Capacity",
            "Unit_Price",
            "Supplier",
            "Created_At",
        ],
        inv,
    )

    mach = [
        [
            d,
            rng.choice(machines),
            "Running",
            92.5,
            75.0,
            1.75,
            82.5,
            0,
            rng.choice(lines),
            f"{d}T08:00:00",
        ]
        for d in dates
        for _ in range(8)
    ]
    write(
        "machine.csv",
        [
            "Date",
            "Machine_ID",
            "Status",
            "Speed_RPM",
            "Temperature_C",
            "Vibration_mm",
            "Power_Usage_pct",
            "Downtime_min",
            "Line",
            "Created_At",
        ],
        mach,
    )

    work = [
        [d, w, rng.choice(lines), rng.choice(shifts), 8.0, 80, 1, "Present", 0.5, f"{d}T08:00:00"]
        for d in dates
        for w in workers
    ]
    write(
        "workers.csv",
        [
            "Date",
            "Worker_ID",
            "Line",
            "Shift",
            "Hours_Worked",
            "Units_Produced",
            "Defects_Caused",
            "Attendance",
            "Overtime_hrs",
            "Created_At",
        ],
        work,
    )


def _has_data() -> bool:
    return bool(glob.glob(os.path.join(DATA_RAW_DIR, "*.csv")))


@pytest.fixture(scope="session", autouse=True)
def sample_data():
    """Generate data/raw/*.csv if the repository has none (bare clone)."""
    if not _has_data():
        try:
            from scripts.generate_sample_data import generate

            print("\n[conftest] data/raw is empty - generating sample data (seed 42)")
            generate(quiet=True)
        except ImportError:
            print("\n[conftest] numpy/pandas/faker absent - stdlib fallback seed")
            _fallback_seed()
        print(
            f"[conftest] generated: {len(glob.glob(os.path.join(DATA_RAW_DIR, '*.csv')))} CSV files"
        )
    yield DATA_RAW_DIR
