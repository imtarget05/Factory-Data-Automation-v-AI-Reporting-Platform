#!/usr/bin/env python3
"""Micro-benchmark: synthetic CSV ETL aggregation timing (stdlib csv only).

Generates N synthetic production rows in-memory, parses via csv module,
aggregates OEE inputs (produced/defects/downtime) per line. No pandas,
no repo imports — always runnable. Never fails.

Run: python3 scripts/bench_factory.py   (from repo root)
"""
import csv
import io
import random
import statistics
import time

N_ROWS = 5000
N_ITERS = 20
LINES = ["LINE-A", "LINE-B", "LINE-C"]


def make_csv(n=N_ROWS, seed=42):
    rng = random.Random(seed)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["line", "produced", "defects", "downtime_min", "target"])
    for i in range(n):
        line = LINES[i % 3]
        produced = rng.randint(80, 120)
        defects = rng.randint(0, 6)
        w.writerow([line, produced, defects, rng.randint(0, 30), 100])
    buf.seek(0)
    return buf.getvalue()


PAYLOAD = make_csv()


def etl_aggregate(payload=PAYLOAD):
    per_line = {}
    rdr = csv.DictReader(io.StringIO(payload))
    for row in rdr:
        e = per_line.setdefault(row["line"], {"produced": 0, "defects": 0, "down": 0, "n": 0})
        e["produced"] += int(row["produced"])
        e["defects"] += int(row["defects"])
        e["down"] += int(row["downtime_min"])
        e["n"] += 1
    # OEE-ish rollup: quality = good/produced, availability proxy from downtime
    out = {}
    for line, e in per_line.items():
        quality = (e["produced"] - e["defects"]) / e["produced"] if e["produced"] else 0.0
        out[line] = {"rows": e["n"], "quality": round(quality, 4)}
    return out


def main():
    samples = []
    for _ in range(N_ITERS):
        t0 = time.perf_counter()
        etl_aggregate()
        samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    mean = statistics.fmean(samples)
    p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))]
    result = etl_aggregate()
    total_rows = sum(v["rows"] for v in result.values())
    print(f"rows_per_iter: {total_rows}")
    print(f"{'op':<18}{'n':>8}{'mean_ms':>12}{'p95_ms':>12}")
    print(f"{'csv_etl_agg':<18}{N_ITERS:>8}{mean:>12.4f}{p95:>12.4f}")


if __name__ == "__main__":
    main()
