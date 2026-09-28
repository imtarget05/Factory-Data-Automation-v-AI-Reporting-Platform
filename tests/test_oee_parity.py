"""FDA-020: OEE parity — pandas calculate_oee vs independent sqlite3 leg.

Both legs run over the SAME cleaned frames from the real data/raw set.
The sqlite3 leg (stdlib, offline-required) re-aggregates with GROUP BY day;
per-day ratios + round() mirror app/etl/kpi_engine.py::calculate_oee exactly
(formula replicated, grouping engine independent). All four components must
match within 1e-6 on every day. An optional duckdb leg runs when duckdb is
importable (importorskip-gated, never required).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas", reason="OEE parity needs pandas")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.etl.kpi_engine import calculate_oee  # noqa: E402

TOL = 1e-6
COMPONENTS = ["Availability_pct", "Performance_pct", "Quality_pct", "OEE_pct"]


@pytest.fixture(scope="module")
def cleaned():
    from app.etl.pipeline import load_and_clean_all

    datasets = load_and_clean_all()
    assert "production" in datasets and "machine" in datasets
    return datasets


def _day_str(series) -> list[str]:
    return pd.to_datetime(series).dt.strftime("%Y-%m-%d").tolist()


def _sqlite_oee(prod: pd.DataFrame, mach: pd.DataFrame) -> pd.DataFrame:
    """Independent OEE via SQL GROUP BY day; ratios/rounding mirror kpi_engine."""
    con = sqlite3.connect(":memory:")
    try:
        cur = con.cursor()
        cur.execute("CREATE TABLE production(day TEXT, target REAL, actual REAL, good REAL)")
        cur.executemany(
            "INSERT INTO production VALUES (?,?,?,?)",
            zip(
                _day_str(prod["Date"]),
                [float(v) for v in prod["Target_Qty"]],
                [float(v) for v in prod["Actual_Qty"]],
                [float(v) for v in prod["Good_Qty"]],
            ),
        )
        cur.execute("CREATE TABLE machine(day TEXT, downtime REAL)")
        cur.executemany(
            "INSERT INTO machine VALUES (?,?)",
            zip(
                _day_str(mach["Date"]),
                [float(v) for v in mach["Downtime_min"]],
            ),
        )
        avail = {
            day: (n, dt)
            for day, n, dt in cur.execute(
                "SELECT day, COUNT(downtime), SUM(downtime) FROM machine GROUP BY day"
            )
        }
        perf = {
            day: (ta, tt)
            for day, ta, tt in cur.execute(
                "SELECT day, SUM(actual), SUM(target) FROM production GROUP BY day"
            )
        }
        qual = {
            day: (g, a)
            for day, g, a in cur.execute(
                "SELECT day, SUM(good), SUM(actual) FROM production GROUP BY day"
            )
        }
    finally:
        con.close()

    rows = []
    for day in sorted(set(avail) | set(perf) | set(qual)):
        n, dt = avail.get(day, (0, 0.0))
        availability = round(((n * 10 - (dt or 0.0)) / (n * 10 if n * 10 else 1)) * 100, 2)
        ta, tt = perf.get(day, (0.0, 0.0))
        performance = round((ta / (tt if tt else 1)) * 100, 2)
        g, a = qual.get(day, (0.0, 0.0))
        quality = round((g / (a if a else 1)) * 100, 2)
        oee = round((availability / 100) * (performance / 100) * (quality / 100) * 100, 2)
        rows.append(
            {
                "Date": pd.Timestamp(day),
                "Availability_pct": availability,
                "Performance_pct": performance,
                "Quality_pct": quality,
                "OEE_pct": oee,
            }
        )
    return pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)


def _norm(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["Date"] = pd.to_datetime(out["Date"])
    return out.sort_values("Date").reset_index(drop=True)


def _assert_parity(left: pd.DataFrame, right: pd.DataFrame, leg: str) -> None:
    assert len(left) == len(right) > 0, f"{leg}: day count {len(left)} vs {len(right)}"
    assert (left["Date"].values == right["Date"].values).all(), f"{leg}: day mismatch"
    for col in COMPONENTS:
        diff = (left[col].astype(float) - right[col].astype(float)).abs()
        assert (diff <= TOL).all(), f"{leg}: {col} max diff {diff.max()}"


def test_oee_sqlite_parity(cleaned):
    """Required offline leg: sqlite3 GROUP BY day matches calculate_oee."""
    pandas_oee = _norm(calculate_oee(cleaned["production"], cleaned["machine"]))
    sqlite_oee = _norm(_sqlite_oee(cleaned["production"], cleaned["machine"]))
    _assert_parity(pandas_oee, sqlite_oee, "sqlite3")


def test_oee_duckdb_parity(cleaned):
    """Optional leg: duckdb aggregation matches too (skipped if absent)."""
    duckdb = pytest.importorskip("duckdb", reason="duckdb not installed (optional leg)")
    prod = cleaned["production"].copy()
    prod["day"] = pd.to_datetime(prod["Date"]).dt.strftime("%Y-%m-%d")
    mach = cleaned["machine"].copy()
    mach["day"] = pd.to_datetime(mach["Date"]).dt.strftime("%Y-%m-%d")
    con = duckdb.connect()
    try:
        con.register("production", prod)
        con.register("machine", mach)
        perf = {
            r[0]: (r[1], r[2])
            for r in con.execute(
                "SELECT day, SUM(Actual_Qty), SUM(Target_Qty) FROM production GROUP BY day"
            ).fetchall()
        }
        qual = {
            r[0]: (r[1], r[2])
            for r in con.execute(
                "SELECT day, SUM(Good_Qty), SUM(Actual_Qty) FROM production GROUP BY day"
            ).fetchall()
        }
        avail = {
            r[0]: (r[1], r[2])
            for r in con.execute(
                "SELECT day, COUNT(Downtime_min), SUM(Downtime_min) FROM machine GROUP BY day"
            ).fetchall()
        }
    finally:
        con.close()
    rows = []
    for day in sorted(set(avail) | set(perf) | set(qual)):
        n, dt = avail.get(day, (0, 0.0))
        availability = round(((n * 10 - (dt or 0.0)) / (n * 10 if n * 10 else 1)) * 100, 2)
        ta, tt = perf.get(day, (0.0, 0.0))
        performance = round((ta / (tt if tt else 1)) * 100, 2)
        g, a = qual.get(day, (0.0, 0.0))
        quality = round((g / (a if a else 1)) * 100, 2)
        oee = round((availability / 100) * (performance / 100) * (quality / 100) * 100, 2)
        rows.append(
            {
                "Date": pd.Timestamp(day),
                "Availability_pct": availability,
                "Performance_pct": performance,
                "Quality_pct": quality,
                "OEE_pct": oee,
            }
        )
    duck_oee = _norm(pd.DataFrame(rows))
    _assert_parity(
        _norm(calculate_oee(cleaned["production"], cleaned["machine"])), duck_oee, "duckdb"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
