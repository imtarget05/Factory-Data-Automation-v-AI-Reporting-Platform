"""
ETL Pipeline: Data Import, Cleaning, and Validation.
Auto-detects and loads CSV/Excel files from raw data directory.
"""

import glob
import logging
import os
from datetime import datetime
from typing import Optional

import pandas as pd

from app.utils.config import DATA_PROCESSED_DIR, DATA_RAW_DIR
from app.utils.logging_config import get_logger, log_event

logger = get_logger("etl", "pipeline")


def discover_files(directory: Optional[str] = None) -> dict[str, str]:
    """Auto-discover data files in the directory."""
    if directory is None:
        directory = DATA_RAW_DIR

    os.makedirs(directory, exist_ok=True)
    files = {}

    patterns = {
        "production": ["production", "prod"],
        "quality": ["quality", "qual"],
        "inventory": ["inventory", "inv", "stock"],
        "machine": ["machine", "mach", "equipment"],
        "workers": ["workers", "worker", "employee", "staff"],
    }

    all_files = []
    for ext in ["*.csv", "*.xlsx", "*.xls"]:
        all_files.extend(glob.glob(os.path.join(directory, ext)))

    for dataset, patterns_list in patterns.items():
        for f in all_files:
            basename = (
                os.path.basename(f)
                .lower()
                .replace(".csv", "")
                .replace(".xlsx", "")
                .replace(".xls", "")
            )
            if dataset in basename or any(p in basename for p in patterns_list):
                if dataset not in files:
                    files[dataset] = f
                break

    # Debug output
    if files:
        print(f"Discovered files: { {k: os.path.basename(v) for k, v in files.items()} }")
    else:
        print(f"WARNING: No data files found in {directory}")
        print(
            f"Available files: {[os.path.basename(f) for f in glob.glob(os.path.join(directory, '*.*'))]}"
        )

    return files


def load_file(filepath: str) -> Optional[pd.DataFrame]:
    """Load a single file (CSV or Excel) into DataFrame."""
    ext = os.path.splitext(filepath)[1].lower()

    try:
        if ext == ".csv":
            return pd.read_csv(filepath)
        elif ext == ".xlsx":
            return pd.read_excel(filepath, engine="openpyxl")
        elif ext == ".xls":
            return pd.read_excel(filepath, engine="xlrd")
        else:
            logger.warning(f"Unsupported file format: {ext}")
            return None
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
        return None


def clean_dataframe(df: pd.DataFrame, dataset_name: str) -> pd.DataFrame:
    """
    Auto-clean: remove duplicates, fill missing values,
    detect invalid values, convert datetimes.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # Remove duplicates
    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        print(f"  Removed {before - len(df)} duplicates from {dataset_name}")

    # Handle missing values
    for col in df.columns:
        missing_count = df[col].isnull().sum()
        if missing_count > 0:
            if df[col].dtype in ["int64", "float64"]:
                df[col] = df[col].fillna(df[col].median())
            elif df[col].dtype == "object":
                df[col] = df[col].fillna(f"Unknown_{col}")
            elif "datetime" in str(df[col].dtype):
                df[col] = df[col].ffill()

    # Convert date columns to datetime
    date_cols = [col for col in df.columns if "date" in col.lower() or col == "Date"]
    for col in date_cols:
        try:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        except Exception:
            pass

    # Standardize text columns (strip whitespace, uppercase first letters)
    for col in df.select_dtypes(include=["object"]).columns:
        try:
            df[col] = df[col].astype(str).str.strip()
        except Exception:
            pass

    # Remove negative quantities where not expected
    for col in [
        "Target_Qty",
        "Actual_Qty",
        "Good_Qty",
        "Reject_Qty",
        "Stock_Qty",
        "Defect_Count",
        "Inspected_Qty",
        "Units_Produced",
    ]:
        if col in df.columns:
            df[col] = df[col].clip(lower=0)

    log_event(logger, "data_cleaned", component="etl", dataset=dataset_name, rows=len(df))
    return df


def load_and_clean_all(directory: Optional[str] = None) -> dict[str, pd.DataFrame]:
    """Discover, load, and clean all datasets."""
    files = discover_files(directory)

    if not files:
        log_event(
            logger,
            "no_files_found",
            level=logging.WARNING,
            component="etl",
            directory=directory if directory else DATA_RAW_DIR,
        )
        return {}

    log_event(logger, "etl_start", component="etl", datasets_found=list(files.keys()))

    datasets = {}
    for dataset_name, filepath in sorted(files.items()):
        log_event(
            logger,
            "loading_dataset",
            component="etl",
            dataset=dataset_name,
            file=os.path.basename(filepath),
        )
        df = load_file(filepath)
        if df is not None:
            df = clean_dataframe(df, dataset_name)
            datasets[dataset_name] = df
        else:
            log_event(
                logger, "load_failed", level=logging.ERROR, component="etl", dataset=dataset_name
            )

    log_event(logger, "etl_complete", component="etl", datasets_loaded=list(datasets.keys()))
    return datasets


def save_processed(datasets: dict[str, pd.DataFrame], directory: Optional[str] = None):
    """Save cleaned datasets to processed directory."""
    if directory is None:
        directory = DATA_PROCESSED_DIR

    os.makedirs(directory, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for name, df in datasets.items():
        filepath = os.path.join(directory, f"{name}_{timestamp}.parquet")
        df.to_parquet(filepath, index=False)
        log_event(
            logger,
            "saved_processed",
            component="etl",
            dataset=name,
            filepath=os.path.basename(filepath),
        )

    log_event(logger, "all_processed_saved", component="etl", directory=directory)


def run_etl(directory: Optional[str] = None) -> dict[str, pd.DataFrame]:
    """Run the full ETL pipeline."""
    datasets = load_and_clean_all(directory)
    if datasets:
        save_processed(datasets)
    return datasets


if __name__ == "__main__":
    datasets = run_etl()
    for name, df in datasets.items():
        print(f"\n{name.upper()} - Shape: {df.shape}")
        print(df.head(3).to_string())
