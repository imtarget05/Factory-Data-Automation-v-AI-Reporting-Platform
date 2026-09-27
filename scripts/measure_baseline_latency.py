"""Phase-1 baseline latency probe (stdlib only, never fails).

Two modes, both honest about what they measure:
  1. LIVE API  — GET {BASE_URL}/api/v1/kpis (+ /api/v1/health) N times when the
     FastAPI service is reachable (2s timeout). Unreachable -> api_latency_ms
     recorded as null (UNMEASURED, to be filled in CI with deps).
  2. OFFLINE ETL — stdlib timing of the pipeline stages that need no third-party
     deps: file discovery + CSV read + group-by aggregation over data/raw/.
     This is a stage proxy, NOT the API latency; labels say so.

Writes benchmarks/baseline_phase1.json (machine, timestamp, dataset rows,
api timings or null, etl stage timings) for Phase-4 comparison.

Usage: python scripts/measure_baseline_latency.py [--base-url URL] [--n 20]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import platform
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
OUT_PATH = os.path.join(REPO_ROOT, "benchmarks", "baseline_phase1.json")


def _p95(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(0.95 * (len(s) - 1)))]


def _get(url: str, timeout: float) -> tuple[int | None, float | None]:
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read()
            return r.status, (time.perf_counter() - t0) * 1000.0
    except Exception:
        return None, None


def live_api(base_url: str, n: int) -> dict:
    health, _ = _get(base_url.rstrip("/") + "/api/v1/health", 2.0)
    if health is None:
        return {"reachable": False, "api_latency_ms": None, "note": "UNMEASURED offline (service down)"}
    samples: list[float] = []
    for _ in range(n):
        status, ms = _get(base_url.rstrip("/") + "/api/v1/kpis", 10.0)
        if status == 200 and ms is not None:
            samples.append(ms)
    return {
        "reachable": True,
        "samples": len(samples),
        "api_latency_ms": {
            "mean": round(statistics.mean(samples), 1) if samples else None,
            "p95": round(_p95(samples), 1) if samples else None,
        },
    }


def offline_etl() -> dict:
    stages: dict[str, float] = {}
    t0 = time.perf_counter()
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.csv")))
    stages["discovery_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    t0 = time.perf_counter()
    rows = 0
    per_day: dict[str, int] = {}
    for path in files:
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    rows += 1
                    day = (row.get("Date") or "")[:10]
                    per_day[day] = per_day.get(day, 0) + 1
        except OSError:
            continue
    stages["read_csv_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    t0 = time.perf_counter()
    total = sum(per_day.values())
    assert total == rows  # aggregation conservation invariant
    stages["groupby_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    return {"files": len(files), "rows": rows, "stages_ms": stages,
            "note": "STDLIB STAGE PROXY — not API latency"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()

    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "machine": platform.platform(),
        "base_url": args.base_url,
        "api": live_api(args.base_url, args.n),
        "etl_proxy": offline_etl(),
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    api = result["api"]
    etl = result["etl_proxy"]
    print(f"API reachable : {api['reachable']}")
    if api["reachable"]:
        print(f"API /kpis     : mean {api['api_latency_ms']['mean']} ms, "
              f"p95 {api['api_latency_ms']['p95']} ms over {api['samples']} samples")
    else:
        print("API /kpis     : UNMEASURED (service unreachable offline)")
    print(f"ETL proxy     : {etl['rows']} rows / {etl['files']} files, "
          f"read {etl['stages_ms']['read_csv_ms']} ms, groupby {etl['stages_ms']['groupby_ms']} ms")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
