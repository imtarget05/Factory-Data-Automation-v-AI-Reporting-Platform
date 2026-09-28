"""FDA-009: Automated Engine Parity Test — Pandas vs Polars.

Verifies that app/etl/pipeline.py (Pandas) and app/etl/polars_etl.py (Polars)
produce equivalent cleaning results, row counts, and KPI aggregations
when given identical source data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pd = pytest.importorskip("pandas", reason="Engine parity test requires pandas")
pl = pytest.importorskip("polars", reason="Engine parity test requires polars")

from app.etl.kpi_engine import calculate_oee  # noqa: E402
from app.etl.pipeline import clean_dataframe, discover_files, load_file  # noqa: E402
from app.etl.polars_etl import clean_polars, discover_files_polars, load_file_polars  # noqa: E402

TOL = 1e-6
OEE_COMPONENTS = ["Availability_pct", "Performance_pct", "Quality_pct", "OEE_pct"]


@pytest.fixture
def sample_production_data():
    return {
        "Date": ["2026-01-01", "2026-01-02", "2026-01-02", "2026-01-03", "2026-01-04"],
        "Target_Qty": [100.0, -15.0, -15.0, None, 200.0],
        "Actual_Qty": [95.0, 50.0, 50.0, 80.0, 190.0],
        "Good_Qty": [90.0, 48.0, 48.0, 75.0, 180.0],
        "Reject_Qty": [5.0, 2.0, 2.0, 5.0, 10.0],
        "Machine_ID": ["M1", "M2", "M2", None, "M1"],
    }


def test_pandas_polars_clean_parity(sample_production_data):
    """FDA-009: Test cleaning parity on synthetic dataset with nulls, negatives, and duplicates."""
    pdf = pd.DataFrame(sample_production_data)
    pldf = pl.DataFrame(sample_production_data)

    p_cleaned = clean_dataframe(pdf.copy(), "production")
    pol_cleaned = clean_polars(pldf.clone(), "production")

    # 1. Row count parity after deduplication
    assert len(p_cleaned) == pol_cleaned.height, (
        f"Row count mismatch: Pandas={len(p_cleaned)} vs Polars={pol_cleaned.height}"
    )

    # 2. Both engines clip negative quantities to 0
    assert (p_cleaned["Target_Qty"] >= 0).all()
    assert (pol_cleaned["Target_Qty"] >= 0).all()

    # 3. Aggregate totals for production quantities must match
    for col in ["Actual_Qty", "Good_Qty", "Reject_Qty"]:
        pandas_sum = float(p_cleaned[col].sum())
        polars_sum = float(pol_cleaned[col].sum())
        assert abs(pandas_sum - polars_sum) < TOL, (
            f"Sum mismatch on {col}: Pandas={pandas_sum} vs Polars={polars_sum}"
        )


def test_pandas_polars_raw_file_loading_parity():
    """FDA-009: Test file load parity between Pandas and Polars on real raw data."""
    p_files = discover_files()
    pol_files = discover_files_polars()

    assert set(p_files.keys()) == set(pol_files.keys()), (
        f"Discovered datasets mismatch: {p_files.keys()} vs {pol_files.keys()}"
    )

    for name in sorted(p_files.keys()):
        p_df = load_file(p_files[name])
        pol_df = load_file_polars(pol_files[name])

        assert p_df is not None and pol_df is not None
        # Raw file row count before cleaning must be byte-identical
        assert len(p_df) == pol_df.height, (
            f"Raw row count mismatch on {name}: Pandas={len(p_df)} vs Polars={pol_df.height}"
        )


def test_pandas_polars_kpi_parity():
    """FDA-009: Compare aggregated KPI calculations between Pandas and Polars on raw production data."""
    p_files = discover_files()
    if "production" not in p_files:
        pytest.skip("No production data file available for KPI parity")

    p_raw = load_file(p_files["production"])
    pol_raw = load_file_polars(p_files["production"])

    # Quality rate: Good_Qty / Actual_Qty
    p_good = float(p_raw["Good_Qty"].sum())
    p_actual = float(p_raw["Actual_Qty"].sum())
    p_quality = p_good / p_actual if p_actual > 0 else 0.0

    pol_good = float(pol_raw["Good_Qty"].sum())
    pol_actual = float(pol_raw["Actual_Qty"].sum())
    pol_quality = pol_good / pol_actual if pol_actual > 0 else 0.0

    assert abs(p_good - pol_good) < TOL
    assert abs(p_actual - pol_actual) < TOL
    assert abs(p_quality - pol_quality) < TOL, (
        f"Quality rate disparity: Pandas={p_quality} vs Polars={pol_quality}"
    )


def test_pandas_polars_oee_parity():
    """FDA-009 / DEF-FACT-002: full OEE parity between engines on the same dataset.

    Both engines clean the SAME raw production + machine files; calculate_oee
    then runs on each engine's cleaned output (polars frame converted via
    .to_pandas()). Row counts must match exactly and all four OEE components
    must agree within 1e-6 on every day.
    """
    prod_csv = REPO_ROOT / "data" / "raw" / "production.csv"
    mach_csv = REPO_ROOT / "data" / "raw" / "machine.csv"
    if not prod_csv.exists() or not mach_csv.exists():
        pytest.skip("Required raw CSVs not present")

    # Same dataset through BOTH engines
    p_prod = clean_dataframe(pd.read_csv(prod_csv), "production")
    p_mach = clean_dataframe(pd.read_csv(mach_csv), "machine")
    pol_prod = clean_polars(pl.read_csv(prod_csv), "production").to_pandas()
    pol_mach = clean_polars(pl.read_csv(mach_csv), "machine").to_pandas()

    # 1. Row count parity after cleaning
    assert len(p_prod) == len(pol_prod) > 0, (
        f"Production row mismatch: Pandas={len(p_prod)} vs Polars={len(pol_prod)}"
    )
    assert len(p_mach) == len(pol_mach) > 0, (
        f"Machine row mismatch: Pandas={len(p_mach)} vs Polars={len(pol_mach)}"
    )

    # 2. OEE parity on all four components within 1e-6 per day
    oee_pd = calculate_oee(p_prod, p_mach).sort_values("Date").reset_index(drop=True)
    oee_pl = calculate_oee(pol_prod, pol_mach).sort_values("Date").reset_index(drop=True)
    assert len(oee_pd) == len(oee_pl) > 0, (
        f"OEE day count mismatch: Pandas={len(oee_pd)} vs Polars={len(oee_pl)}"
    )
    assert (pd.to_datetime(oee_pd["Date"]).values == pd.to_datetime(oee_pl["Date"]).values).all(), (
        "OEE day mismatch between engines"
    )
    for col in OEE_COMPONENTS:
        diff = (oee_pd[col].astype(float) - oee_pl[col].astype(float)).abs()
        assert (diff <= TOL).all(), f"OEE {col} max diff {diff.max()}"
