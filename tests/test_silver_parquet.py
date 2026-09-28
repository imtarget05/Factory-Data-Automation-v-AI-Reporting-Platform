"""FDA-018/019: silver parquet export (snappy) roundtrip test.

Engine honesty: uses the polars path if polars is importable, else the
pandas+pyarrow path. If NEITHER is available the parquet test skips and the
CSV-gzip fallback test runs instead (mark FDA-018/019 PARTIAL in that case).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas", reason="silver export needs pandas")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.etl.medallion import (  # noqa: E402
    available_engines,
    export_silver_production,
)

try:
    import polars  # noqa: F401

    _HAS_POLARS = True
except Exception:
    _HAS_POLARS = False

try:
    import pyarrow  # noqa: F401

    _HAS_PYARROW = True
except Exception:
    _HAS_PYARROW = False

_HAS_PARQUET = _HAS_POLARS or _HAS_PYARROW

KEY_COLUMNS = ["Date", "Target_Qty", "Actual_Qty", "Good_Qty", "Reject_Qty"]


@pytest.fixture(scope="module")
def cleaned():
    from app.etl.pipeline import load_and_clean_all

    datasets = load_and_clean_all()
    assert "production" in datasets, "no production frame from real data/raw"
    return datasets


@pytest.mark.skipif(not _HAS_PARQUET, reason="needs polars or pyarrow for parquet")
def test_silver_parquet_roundtrip(cleaned, tmp_path):
    """Row count + key columns survive a snappy parquet roundtrip."""
    info = export_silver_production(cleaned, outdir=str(tmp_path))
    assert info["engine"] in ("polars", "pandas+pyarrow")
    assert os.path.exists(info["path"])

    src = cleaned["production"]
    if _HAS_POLARS and not isinstance(src, pd.DataFrame):
        import polars as pl

        back = pl.read_parquet(info["path"]).to_pandas()
        src_cmp = src.to_pandas()
    else:
        back = pd.read_parquet(info["path"], engine="pyarrow")
        src_cmp = src

    assert len(back) == len(src_cmp) == info["rows"]
    assert set(back.columns) == set(src_cmp.columns)
    for col in KEY_COLUMNS:
        assert col in back.columns, f"key column {col} missing after roundtrip"
        left = pd.Series(src_cmp[col].astype(str).tolist())
        right = pd.Series(back[col].astype(str).tolist())
        assert (left.values == right.values).all(), f"key column {col} mismatch"


@pytest.mark.skipif(not _HAS_PARQUET, reason="needs polars or pyarrow for parquet")
def test_silver_parquet_smaller_than_csv(cleaned, tmp_path):
    """Snappy parquet must beat the equivalent CSV on disk."""
    info = export_silver_production(cleaned, outdir=str(tmp_path))
    csv_path = str(tmp_path / "production.csv")
    cleaned["production"].to_csv(csv_path, index=False)
    assert os.path.getsize(info["path"]) < os.path.getsize(csv_path), (
        f"parquet {os.path.getsize(info['path'])} >= csv {os.path.getsize(csv_path)}"
    )


def test_engine_report_matches_reality():
    engines = available_engines()
    assert engines == {"polars": _HAS_POLARS, "pyarrow": _HAS_PYARROW}


@pytest.mark.skipif(_HAS_PARQUET, reason="parquet available; fallback not needed")
def test_csv_gzip_fallback_when_no_parquet_engine(cleaned, tmp_path):
    """Offline fallback keeps a silver artefact when no engine installs."""
    from app.etl.medallion import export_silver_production_csv_gzip

    info = export_silver_production_csv_gzip(cleaned, outdir=str(tmp_path))
    assert info["engine"] == "csv-gzip"
    back = pd.read_csv(info["path"], compression="gzip")
    assert len(back) == len(cleaned["production"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
