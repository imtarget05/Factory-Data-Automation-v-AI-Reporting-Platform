"""
Polars-based ETL pipeline for high-performance data processing.
Alternative to Pandas for large datasets (100k+ rows).
Uses lazy evaluation for optimal memory usage.
"""
import os
import glob
import polars as pl
from typing import Dict, Optional
from datetime import datetime
from app.utils.config import DATA_RAW_DIR, DATA_PROCESSED_DIR


def discover_files_polars(directory: Optional[str] = None) -> Dict[str, str]:
    """Auto-discover data files (supports date-prefixed files like 2026-01-01.xlsx)."""
    if directory is None:
        directory = DATA_RAW_DIR
    
    os.makedirs(directory, exist_ok=True)
    files = {}
    
    # Collect all CSV/Excel files
    all_files = []
    for ext in ["*.csv", "*.xlsx", "*.xls"]:
        all_files.extend(glob.glob(os.path.join(directory, ext)))
    
    # Group by dataset type (supports both name-based and date-prefixed)
    for f in all_files:
        basename = os.path.basename(f).lower()
        name_no_ext = basename.replace(".csv", "").replace(".xlsx", "").replace(".xls", "")
        
        # Detect dataset type from filename
        dataset_type = None
        for dtype in ["production", "quality", "inventory", "machine", "workers"]:
            if dtype in name_no_ext:
                dataset_type = dtype
                break
        
        # Also detect date-prefixed files: 2026-01-01_production.xlsx
        if dataset_type is None:
            parts = name_no_ext.split("_")
            if len(parts) >= 2:
                for dtype in ["production", "quality", "inventory", "machine", "workers"]:
                    if dtype in parts[-1]:
                        dataset_type = dtype
                        break
        
        if dataset_type and dataset_type not in files:
            files[dataset_type] = f
    
    return files


def load_file_polars(filepath: str) -> Optional[pl.DataFrame]:
    """Load a file using Polars (supports CSV and Excel)."""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".csv":
            return pl.read_csv(filepath, try_parse_dates=True)
        elif ext in [".xlsx", ".xls"]:
            # Polars doesn't natively read Excel, use pandas bridge
            import pandas as pd
            pdf = pd.read_excel(filepath, engine="openpyxl")
            return pl.from_pandas(pdf)
        else:
            print(f"Unsupported format: {ext}")
            return None
    except Exception as e:
        print(f"Error loading {filepath} with Polars: {e}")
        return None


def clean_polars(df: pl.DataFrame, dataset_name: str) -> pl.DataFrame:
    """Clean data using Polars operations."""
    if df is None or df.is_empty():
        return df
    
    before = df.height
    
    # Remove duplicates
    df = df.unique()
    if df.height < before:
        print(f"  [Polars] Removed {before - df.height} duplicates from {dataset_name}")
    
    # Fill nulls
    for col in df.columns:
        if df[col].is_null().sum() > 0:
            if df[col].dtype in [pl.Int64, pl.Float64]:
                median_val = df[col].median()
                df = df.with_columns(df[col].fill_null(median_val))
            elif df[col].dtype == pl.Utf8:
                df = df.with_columns(df[col].fill_null(f"Unknown_{col}"))
    
    # Convert date columns
    date_cols = [c for c in df.columns if "date" in c.lower() or c == "Date"]
    for col in date_cols:
        try:
            df = df.with_columns(df[col].str.strptime(pl.Date, format="%Y-%m-%d", strict=False))
        except:
            pass
    
    # Clip negative values
    for col in ["Target_Qty", "Actual_Qty", "Good_Qty", "Reject_Qty", "Stock_Qty"]:
        if col in df.columns:
            df = df.with_columns(
                pl.when(df[col] < 0).then(pl.lit(0)).otherwise(df[col]).alias(col)
            )
    
    print(f"  [Polars] Cleaned {dataset_name}: {df.height} rows")
    return df


def run_etl_polars(directory: Optional[str] = None) -> Dict[str, pl.DataFrame]:
    """Run ETL pipeline using Polars."""
    files = discover_files_polars(directory)
    
    if not files:
        print("No data files found.")
        return {}
    
    print(f"\n{'='*60}")
    print("Polars ETL Pipeline")
    print(f"{'='*60}")
    
    datasets = {}
    for name, filepath in sorted(files.items()):
        print(f"\nLoading {name} from: {os.path.basename(filepath)}")
        df = load_file_polars(filepath)
        if df is not None:
            df = clean_polars(df, name)
            datasets[name] = df
    
    return datasets


def benchmark_comparison():
    """Compare Pandas vs Polars performance."""
    import time
    
    print("\n" + "="*60)
    print("Performance Benchmark: Pandas vs Polars")
    print("="*60)
    
    files = discover_files_polars()
    
    for name, filepath in sorted(files.items()):
        print(f"\n--- {name} ({os.path.basename(filepath)}) ---")
        
        # Pandas
        t0 = time.time()
        import pandas as pd
        pdf = pd.read_csv(filepath)
        t1 = time.time()
        print(f"  Pandas load: {t1-t0:.3f}s ({len(pdf)} rows)")
        
        # Polars
        t0 = time.time()
        ldf = pl.read_csv(filepath, try_parse_dates=True)
        t1 = time.time()
        print(f"  Polars load: {t1-t0:.3f}s ({ldf.height} rows)")
        
        # Speed comparison
        ratio = (t1 - t0) / (t1 - t0 + 0.001)
        print(f"  Polars is {'faster' if t1-t0 < t1-t0 else 'slower'}")


if __name__ == "__main__":
    datasets = run_etl_polars()
    for name, df in datasets.items():
        print(f"\n{name}: {df.shape}")