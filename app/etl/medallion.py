"""Medallion silver export: cleaned production frame -> snappy parquet.

Additive module (FDA-018/019). Does NOT touch app/etl/pipeline.py.

Engine selection (honest, no hard dependency):
  1. polars path — if polars is importable, write via
     ``pl.DataFrame.write_parquet(..., compression="snappy")``.
  2. pandas + pyarrow path — otherwise, if pyarrow is importable, write via
     ``pd.DataFrame.to_parquet(..., engine="pyarrow", compression="snappy")``.
  3. neither — raise RuntimeError; callers/tests fall back to the CSV-gzip
     silver file and mark FDA-018/019 PARTIAL.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from app.utils.config import BASE_DIR

SILVER_DIR = os.path.join(BASE_DIR, "data", "silver")
SILVER_PRODUCTION_PARQUET = os.path.join(SILVER_DIR, "production.parquet")
SILVER_PRODUCTION_CSV_GZIP = os.path.join(SILVER_DIR, "production.csv.gz")


def available_engines() -> dict[str, bool]:
    """Report which parquet engines are importable (no side effects)."""
    try:
        import polars  # noqa: F401

        has_polars = True
    except Exception:
        has_polars = False
    try:
        import pyarrow  # noqa: F401

        has_pyarrow = True
    except Exception:
        has_pyarrow = False
    return {"polars": has_polars, "pyarrow": has_pyarrow}


def _as_pandas(frame: Any) -> Any:
    """Coerce a polars frame to pandas; pass pandas frames through."""
    if type(frame).__module__.split(".")[0] == "polars":
        return frame.to_pandas()
    return frame


def export_silver_production(
    datasets: Optional[dict] = None,
    outdir: Optional[str] = None,
    filename: str = "production.parquet",
) -> dict[str, Any]:
    """Export the cleaned production frame to silver parquet (snappy).

    Returns ``{"path": ..., "engine": "polars"|"pandas+pyarrow", "rows": N}``.
    Raises RuntimeError if neither engine is available, KeyError if the
    production frame is missing.
    """
    if datasets is None:
        from app.etl.pipeline import load_and_clean_all

        datasets = load_and_clean_all()
    if "production" not in datasets:
        raise KeyError("no cleaned 'production' frame to export")
    frame = datasets["production"]

    outdir = outdir or SILVER_DIR
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, filename)

    engines = available_engines()
    if engines["polars"]:
        import polars as pl

        pl_frame = frame if isinstance(frame, pl.DataFrame) else pl.from_pandas(frame)
        pl_frame.write_parquet(path, compression="snappy")
        return {"path": path, "engine": "polars", "rows": pl_frame.height}
    if engines["pyarrow"]:
        pdf = _as_pandas(frame)
        pdf.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
        return {"path": path, "engine": "pandas+pyarrow", "rows": len(pdf)}
    raise RuntimeError(
        "no parquet engine available (need polars or pyarrow); "
        "use export_silver_production_csv_gzip fallback"
    )


def export_silver_production_csv_gzip(
    datasets: Optional[dict] = None,
    outdir: Optional[str] = None,
    filename: str = "production.csv.gz",
) -> dict[str, Any]:
    """Stdlib-friendly fallback: gzip-compressed CSV silver file."""
    if datasets is None:
        from app.etl.pipeline import load_and_clean_all

        datasets = load_and_clean_all()
    if "production" not in datasets:
        raise KeyError("no cleaned 'production' frame to export")
    pdf = _as_pandas(datasets["production"])

    outdir = outdir or SILVER_DIR
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, filename)
    pdf.to_csv(path, index=False, compression="gzip")
    return {"path": path, "engine": "csv-gzip", "rows": len(pdf)}
