"""
Deterministic sample-data generator for the Smart Manufacturing Platform.

Why this exists
---------------
`.gitignore` excludes the contents of `data/raw/`, `data/processed/` and
`data/exports/` (it only negates `.gitkeep`), so a fresh `git clone` contains
no input data at all. The ETL test suite calls
`app.etl.pipeline.discover_files()` and asserts that the five expected
datasets exist, so on a bare clone those tests could only ever fail.

This script is the committed, reproducible seed: it writes the five CSVs the
real pipeline discovers and transforms, so a reviewer can go from clone to
green suite in one command. Output is byte-reproducible: the same SEED always
produces byte-identical files, on any machine, on any day. Nothing here
reads the wall clock, the process hash seed, or the environment.

Usage
-----
    python -m scripts.generate_sample_data
    python -m scripts.generate_sample_data --days 30 --output-dir some/dir

The generated data deliberately contains a small amount of dirt (duplicate
rows, missing values, stray whitespace, negative quantities) so that
`clean_dataframe()` in `app/etl/pipeline.py` has real work to do.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.utils.config import (  # noqa: E402
    DEFAULT_SHIFTS,
    MACHINES,
    PRODUCTION_LINES,
    PRODUCTS,
    WORKERS,
)

SEED = 42
START_DATE = datetime(2026, 1, 1)

DEFECT_TYPES = [
    "Scratch",
    "Color Mismatch",
    "Size Error",
    "Material Defect",
    "Stitching Issue",
    "Sole Detachment",
    "Label Error",
    "Packaging Damage",
]
MACHINE_STATUSES = ["Running", "Idle", "Maintenance", "Failure"]
STATUS_WEIGHTS = [0.75, 0.12, 0.08, 0.05]
SEVERITIES = ["Minor", "Major", "Critical"]
SEVERITY_WEIGHTS = [0.6, 0.3, 0.1]


def _dates(days: int) -> list[str]:
    """Calendar dates as ISO strings, starting at START_DATE."""
    return [(START_DATE + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days)]


def _created_at(date_iso: str) -> str:
    """A deterministic ingestion timestamp derived from the record's own date.

    The original generator used `datetime.now()`, which made every run produce
    a different file. Deriving it from the record date keeps the output
    byte-identical between runs.
    """
    return f"{date_iso}T06:00:00"


def _dirty_text(records: list[dict], columns: list[str], rng: random.Random, rate: float = 0.01) -> None:
    """Pad a small fraction of text values with whitespace for the cleaner to strip."""
    for row in records:
        if rng.random() < rate:
            row[rng.choice(columns)] = f"  {row[rng.choice(columns)]}  "


def _blank_values(records: list[dict], columns: list[str], rng: random.Random, rate: float = 0.01) -> None:
    """Set a small fraction of numeric values to None so the imputer has work to do."""
    for row in records:
        if rng.random() < rate:
            row[rng.choice(columns)] = None


def _duplicate_rows(records: list[dict], rng: random.Random, rate: float = 0.01) -> None:
    """Append exact copies of some rows so `drop_duplicates()` has work to do."""
    originals = list(records)
    rng.shuffle(originals)
    for row in originals[: max(1, int(len(originals) * rate))]:
        records.append(dict(row))


def generate_production(days: int, rng: random.Random, nprng: np.random.Generator) -> pd.DataFrame:
    """Production output records: target vs actual, good vs reject, cycle time."""
    records = []
    for date_iso in _dates(days):
        volume = 60 if datetime.strptime(date_iso, "%Y-%m-%d").weekday() >= 5 else 150
        for _ in range(volume):
            target = int(nprng.normal(500, 50) * (0.6 if volume == 60 else 1.0))
            actual = int(target * float(nprng.uniform(0.85, 1.05)))
            good = int(actual * float(nprng.uniform(0.92, 0.99)))
            records.append(
                {
                    "Date": date_iso,
                    "Line": rng.choice(PRODUCTION_LINES),
                    "Shift": rng.choice(DEFAULT_SHIFTS),
                    "Product": rng.choice(PRODUCTS),
                    "Machine_ID": rng.choice(MACHINES),
                    "Worker_ID": rng.choice(WORKERS),
                    "Target_Qty": target,
                    "Actual_Qty": actual,
                    "Good_Qty": good,
                    "Reject_Qty": actual - good,
                    "Cycle_Time_sec": round(float(nprng.uniform(30, 120)), 1),
                    "Created_At": _created_at(date_iso),
                }
            )

    _dirty_text(records, ["Line", "Product", "Shift"], rng)
    _blank_values(records, ["Actual_Qty", "Cycle_Time_sec"], rng)
    _duplicate_rows(records, rng)
    # Impossible negative targets: `clean_dataframe()` clips quantity columns at 0.
    for row in records[:3]:
        row["Target_Qty"] = -row["Target_Qty"]
    return pd.DataFrame(records)


def generate_quality(days: int, rng: random.Random, nprng: np.random.Generator) -> pd.DataFrame:
    """Quality inspection records: defect type, count, severity, inspector."""
    records = []
    for date_iso in _dates(days):
        for _ in range(40):
            records.append(
                {
                    "Date": date_iso,
                    "Product": rng.choice(PRODUCTS),
                    "Line": rng.choice(PRODUCTION_LINES),
                    "Defect_Type": rng.choice(DEFECT_TYPES),
                    "Defect_Count": int(nprng.exponential(3) + 1),
                    "Inspected_Qty": int(nprng.normal(200, 30)),
                    "Severity": rng.choices(SEVERITIES, weights=SEVERITY_WEIGHTS)[0],
                    "Inspector_ID": rng.choice(WORKERS),
                    "Created_At": _created_at(date_iso),
                }
            )

    _dirty_text(records, ["Defect_Type", "Severity"], rng)
    _blank_values(records, ["Defect_Count", "Inspected_Qty"], rng)
    _duplicate_rows(records, rng)
    return pd.DataFrame(records)


def generate_inventory(days: int, rng: random.Random, nprng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    """Daily stock position per product, with a rolling stock balance."""
    records = []
    reorder_points = {p: rng.randint(150, 500) for p in PRODUCTS}
    max_capacity = {p: rng.randint(2000, 5000) for p in PRODUCTS}
    unit_prices = {p: round(rng.uniform(10, 150), 2) for p in PRODUCTS}
    suppliers = {p: fake.company() for p in PRODUCTS}
    # Seeded from the product name, not Python's salted hash(), so the demand
    # profile is identical on every interpreter run.
    stock = {
        p: rng.randint(300, 2000) for p in PRODUCTS
    }

    for date_iso in _dates(days):
        for product in PRODUCTS:
            offset = PRODUCTS.index(product)
            demand = int(nprng.poisson(20 + offset * 3))
            incoming = int(nprng.poisson(15 + offset * 2))
            stock[product] = max(0, min(max_capacity[product], stock[product] + incoming - demand))
            records.append(
                {
                    "Date": date_iso,
                    "Product": product,
                    "Stock_Qty": stock[product],
                    "Incoming_Qty": incoming,
                    "Outgoing_Qty": demand,
                    "Reorder_Point": reorder_points[product],
                    "Max_Capacity": max_capacity[product],
                    "Unit_Price": unit_prices[product],
                    "Supplier": suppliers[product],
                    "Created_At": _created_at(date_iso),
                }
            )

    _blank_values(records, ["Unit_Price"], rng)
    _duplicate_rows(records, rng)
    for row in records[:2]:
        row["Stock_Qty"] = -50
    return pd.DataFrame(records)


def generate_machine(days: int, rng: random.Random, nprng: np.random.Generator) -> pd.DataFrame:
    """Machine telemetry: status, speed, temperature, vibration, power, downtime."""
    records = []
    for date_iso in _dates(days):
        for _ in range(60):
            machine = rng.choice(MACHINES)
            status = rng.choices(MACHINE_STATUSES, weights=STATUS_WEIGHTS)[0]
            if status == "Running":
                speed, temp, vibration, power = 92.5, 75.0, 1.75, 82.5
            elif status == "Idle":
                speed, temp, vibration, power = 0.0, 50.0, 0.3, 10.0
            elif status == "Maintenance":
                speed, temp, vibration, power = 0.0, 30.0, 0.1, 0.0
            else:  # Failure
                speed, temp, vibration, power = 0.0, 40.0, 10.0, 0.0
            down = status in ("Maintenance", "Failure")
            records.append(
                {
                    "Date": date_iso,
                    "Machine_ID": machine,
                    "Status": status,
                    "Speed_RPM": round(speed + float(nprng.uniform(-7.5, 7.5)) if status == "Running" else speed, 1),
                    "Temperature_C": round(temp + float(nprng.uniform(-5, 5)), 1),
                    "Vibration_mm": round(vibration + float(nprng.uniform(-0.25, 0.25)), 2),
                    "Power_Usage_pct": round(power + float(nprng.uniform(-5, 5)) if status == "Running" else power, 1),
                    "Downtime_min": int(nprng.exponential(10)) if down else 0,
                    "Line": rng.choice(PRODUCTION_LINES),
                    "Created_At": _created_at(date_iso),
                }
            )

    _dirty_text(records, ["Machine_ID", "Line"], rng)
    _blank_values(records, ["Temperature_C", "Downtime_min"], rng)
    _duplicate_rows(records, rng)
    return pd.DataFrame(records)


def generate_workers(days: int, rng: random.Random, nprng: np.random.Generator) -> pd.DataFrame:
    """Worker productivity: attendance, hours, units produced, defects caused."""
    records = []
    for date_iso in _dates(days):
        for worker in rng.sample(WORKERS, 80):
            if rng.random() < 0.2:
                continue
            attendance = rng.choices(["Present", "Absent", "Leave"], weights=[0.85, 0.1, 0.05])[0]
            if attendance != "Present":
                continue
            hours = round(float(nprng.uniform(6, 10)), 1)
            units = int(nprng.normal(80, 15) * (hours / 8))
            records.append(
                {
                    "Date": date_iso,
                    "Worker_ID": worker,
                    "Line": rng.choice(PRODUCTION_LINES),
                    "Shift": rng.choice(DEFAULT_SHIFTS),
                    "Hours_Worked": hours,
                    "Units_Produced": units,
                    "Defects_Caused": int(nprng.exponential(2)),
                    "Attendance": attendance,
                    "Overtime_hrs": round(max(0.0, float(nprng.normal(0.5, 0.8))), 1),
                    "Created_At": _created_at(date_iso),
                }
            )

    _dirty_text(records, ["Worker_ID", "Shift"], rng)
    _blank_values(records, ["Units_Produced", "Hours_Worked"], rng)
    _duplicate_rows(records, rng)
    return pd.DataFrame(records)


def build_datasets(days: int = 90) -> dict[str, pd.DataFrame]:
    """Build all five datasets from a freshly seeded set of RNGs."""
    rng = random.Random(SEED)
    nprng = np.random.default_rng(SEED)
    Faker.seed(SEED)
    fake = Faker()
    return {
        "production": generate_production(days, rng, nprng),
        "quality": generate_quality(days, rng, nprng),
        "inventory": generate_inventory(days, rng, nprng, fake),
        "machine": generate_machine(days, rng, nprng),
        "workers": generate_workers(days, rng, nprng),
    }


def write_datasets(datasets: dict[str, pd.DataFrame], output_dir: str) -> dict[str, str]:
    """Write each dataset to `<name>.csv` and return name -> path."""
    os.makedirs(output_dir, exist_ok=True)
    paths = {}
    for name, df in datasets.items():
        path = os.path.join(output_dir, f"{name}.csv")
        # lineterminator is pinned so output is byte-identical on Windows too.
        df.to_csv(path, index=False, lineterminator="\n")
        paths[name] = path
    return paths


def _sha256(path: str) -> str:
    """Content hash of a written file.

    Hashing the bytes on disk rather than the DataFrame in memory is deliberate:
    it catches anything that changes the serialised form (column order, float
    formatting, line terminator), which is exactly the class of drift that makes
    a "deterministic" generator quietly stop being deterministic.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# Bumped whenever the generated schema or dirt distribution changes in a way
# that alters the output bytes. CI asserts the regenerated hashes match the
# committed manifest, so a generator change that was not intentional here fails
# loudly instead of silently invalidating every recorded test artefact.
FIXTURE_SCHEMA_VERSION = "factory-fixture-v1"


def write_manifest(paths: dict[str, str], datasets: dict, days: int) -> dict:
    """Write `data/raw/_fixture_manifest.json` and return it.

    The manifest is what makes `git clone -> generate -> verify -> test` a
    closed loop. Without it a reviewer can only trust that the generator is
    deterministic; with it, any drift between the committed expectation and a
    fresh generation is a hard failure.
    """
    manifest = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "seed": SEED,
        "days": days,
        "datasets": {
            f"{name}.csv": {
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "sha256": _sha256(path),
            }
            for name, (df, path) in ((n, (datasets[n], paths[n])) for n in paths)
        },
    }
    manifest["total_rows"] = sum(d["rows"] for d in manifest["datasets"].values())
    # Hash the manifest itself so a truncated or hand-edited manifest is detected
    # before its contents are trusted.
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = hashlib.sha256(payload.encode()).hexdigest()

    out = os.path.join(os.path.dirname(paths[next(iter(paths))]), "_fixture_manifest.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return manifest


def generate(days: int = 90, output_dir: str = None, quiet: bool = False) -> dict[str, str]:
    """Generate and write all sample data. Returns name -> written path."""
    if output_dir is None:
        from app.utils.config import DATA_RAW_DIR

        output_dir = DATA_RAW_DIR
    datasets = build_datasets(days)
    paths = write_datasets(datasets, output_dir)
    manifest = write_manifest(paths, datasets, days)
    if not quiet:
        total = sum(len(df) for df in datasets.values())
        print(f"Seed {SEED} | {days} days | output: {output_dir}")
        for name, df in datasets.items():
            print(f"  {name + '.csv':<16} {len(df):>7,} rows x {len(df.columns):>2} cols")
        print(f"  {'TOTAL':<16} {total:>7,} rows")
        print(f"  manifest: {manifest['schema_version']} sha256={manifest['manifest_sha256'][:16]}")
    return paths


def main(argv: list[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic factory sample data.")
    parser.add_argument("--days", type=int, default=90, help="number of days to simulate")
    parser.add_argument("--output-dir", default=None, help="defaults to data/raw")
    parser.add_argument(
        "--quiet", action="store_true", help="suppress the per-dataset summary"
    )
    args = parser.parse_args(argv)
    generate(days=args.days, output_dir=args.output_dir, quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
