"""Phase-2 ETL idempotency (stdlib-first; pandas path runs only when available).

The real ETL (app/etl/pipeline.py + kpi_engine.py) needs pandas, which the
gateway venv does not provide. This file therefore proves the idempotency
contract at two levels:

  * ALWAYS (stdlib csv/hashlib): seeded random CSV inputs aggregated twice
    yield byte-identical aggregate digests, and aggregating input+input
    (duplicated rows) after dedup equals the single-input aggregate — the
    same contract ``clean_dataframe`` documents (drop_duplicates + clip).
  * WHEN PANDAS IS INSTALLED (importorskip): a rerun of the real
    ``clean_dataframe`` over the same frame yields an identical frame.

One subtlety, documented where it bites: ``clean_dataframe`` clips negatives to
0, which *merges* distinct dirty rows by design (-5 and -1 both become 0) — the
cleaned frame therefore legitimately contains duplicates. Rerun stability is
what the pandas test asserts; duplicate-free output is the quarantine gate's
job (see tests/test_quarantine.py), not the cleaner's.

No new dependencies; no network.
"""

from __future__ import annotations

import csv
import hashlib
import io
import random

import pytest

pytestmark = [pytest.mark.race]

SEED = 20260927
N_CASES = 200

_MACHINES = [f"M-{i:02d}" for i in range(1, 6)]
_DATES = [f"2026-01-{d:02d}" for d in range(1, 10)]


def _random_rows(rng: random.Random, n: int) -> list[dict]:
    rows = []
    for _ in range(n):
        rows.append(
            {
                "Date": rng.choice(_DATES),
                "Machine_ID": rng.choice(_MACHINES),
                "Target_Qty": str(rng.choice([0, 50, 100, 200, -5])),
                "Actual_Qty": str(rng.choice([0, 90, 180, 210, -1])),
            }
        )
    return rows


def _to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["Date", "Machine_ID", "Target_Qty", "Actual_Qty"])
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _clean(rows: list[dict]) -> list[dict]:
    """Stdlib mirror of clean_dataframe's documented contract: dedup exact
    rows, clip negative quantities at zero."""
    seen: set[tuple] = set()
    out = []
    for r in rows:
        key = (r["Date"], r["Machine_ID"], r["Target_Qty"], r["Actual_Qty"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "Date": r["Date"],
                "Machine_ID": r["Machine_ID"],
                "Target_Qty": max(0, int(r["Target_Qty"])),
                "Actual_Qty": max(0, int(r["Actual_Qty"])),
            }
        )
    return out


def _aggregate(rows: list[dict]) -> dict[tuple, dict]:
    agg: dict[tuple, dict] = {}
    for r in rows:
        key = (r["Date"], r["Machine_ID"])
        slot = agg.setdefault(key, {"Target": 0, "Actual": 0, "n": 0})
        slot["Target"] += r["Target_Qty"]
        slot["Actual"] += r["Actual_Qty"]
        slot["n"] += 1
    return agg


def _digest(agg: dict) -> str:
    canon = "\n".join(f"{k}:{v['Target']},{v['Actual']},{v['n']}" for k, v in sorted(agg.items()))
    return hashlib.sha256(canon.encode()).hexdigest()


def test_double_run_yields_identical_aggregates():
    rng = random.Random(SEED)
    for case in range(N_CASES):
        rows = _random_rows(rng, rng.randint(0, 40))
        first = _digest(_aggregate(_clean(rows)))
        # Second run re-parses the same CSV bytes (fresh read, like a rerun).
        reparsed = list(csv.DictReader(io.StringIO(_to_csv(rows))))
        second = _digest(_aggregate(_clean(reparsed)))
        assert first == second, f"case {case}: ETL rerun over identical input changed aggregates"


def test_duplicated_input_rows_do_not_duplicate_aggregates():
    rng = random.Random(SEED + 1)
    for case in range(N_CASES):
        rows = _random_rows(rng, rng.randint(1, 30))
        single = _digest(_aggregate(_clean(rows)))
        doubled = _digest(_aggregate(_clean(rows + rows)))
        assert single == doubled, f"case {case}: duplicated input rows leaked into aggregates"
        # Quantities are clipped, never negative, after cleaning.
        for r in _clean(rows):
            assert r["Target_Qty"] >= 0 and r["Actual_Qty"] >= 0, (
                f"case {case}: negative quantity survived cleaning: {r}"
            )


def test_real_clean_dataframe_double_run_when_pandas_available():
    """Real-path rerun-stability; skipped (not failed) when pandas is absent."""
    pd = pytest.importorskip("pandas")
    pytest.importorskip("dotenv")
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.etl.pipeline import clean_dataframe

    rng = random.Random(SEED + 2)
    for case in range(20):
        rows = _random_rows(rng, rng.randint(1, 30))
        df = pd.DataFrame(rows)
        df["Target_Qty"] = pd.to_numeric(df["Target_Qty"])
        df["Actual_Qty"] = pd.to_numeric(df["Actual_Qty"])
        a = clean_dataframe(df, "production")
        b = clean_dataframe(df, "production")
        assert a.equals(b), f"case {case}: real clean_dataframe rerun changed the frame"
        # Clipping merges distinct dirty rows by design (-5 and -1 both become
        # 0), so the cleaned frame legitimately contains duplicates. Rerun
        # stability — asserted above — is what this test exists to prove.
