"""
ETL Pipeline: Data Import, Cleaning, and Validation.
Auto-detects and loads CSV/Excel files from raw data directory.
"""
import os
import glob
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Tuple
from app.utils.config import DATA_RAW_DIR, DATA_PROCESSED_DIR


def discover_files(directory: Optional[str] = None) -> Dict[str, str]:
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
            basename = os.path.basename(f).lower().replace(".csv", "").replace(".xlsx", "").replace(".xls", "")
            if dataset in basename or any(p in basename for p in patterns_list):
                if dataset not in files:
                    files[dataset] = f
                break
    
    # Debug output
    if files:
        print(f"Discovered files: { {k: os.path.basename(v) for k, v in files.items()} }")
    else:
        print(f"WARNING: No data files found in {directory}")
        print(f"Available files: {[os.path.basename(f) for f in glob.glob(os.path.join(directory, '*.*'))]}")
    
    return files


def load_file(filepath: str) -> Optional[pd.DataFrame]:
    """Load a single file (CSV or Excel) into DataFrame."""
    ext = os.path.splitext(filepath)[1].lower()
    
    try:
        if ext == ".csv":
            return pd.read_csv(filepath)
        elif ext in [".xlsx", ".xls"]:
            return pd.read_excel(filepath, engine="openpyxl")
        else:
            print(f"Unsupported file format: {ext}")
            return None
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
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
                df[col] = df[col].fillna(method="ffill")
    
    # Convert date columns to datetime
    date_cols = [col for col in df.columns if "date" in col.lower() or col == "Date"]
    for col in date_cols:
        try:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        except:
            pass
    
    # Standardize text columns (strip whitespace, uppercase first letters)
    for col in df.select_dtypes(include=["object"]).columns:
        try:
            df[col] = df[col].astype(str).str.strip()
        except:
            pass
    
    # Remove negative quantities where not expected
    for col in ["Target_Qty", "Actual_Qty", "Good_Qty", "Reject_Qty", "Stock_Qty",
                "Defect_Count", "Inspected_Qty", "Units_Produced"]:
        if col in df.columns:
            df[col] = df[col].clip(lower=0)
    
    print(f"  Cleaned {dataset_name}: {len(df)} rows")
    return df


def load_and_clean_all(directory: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    """Discover, load, and clean all datasets."""
    files = discover_files(directory)
    
    if not files:
        print(f"No data files found in {directory if directory else DATA_RAW_DIR}")
        return {}
    
    print(f"\n{'='*60}")
    print(f"ETL Pipeline - Loading Data")
    print(f"{'='*60}")
    
    datasets = {}
    for dataset_name, filepath in sorted(files.items()):
        print(f"\nLoading {dataset_name} from: {os.path.basename(filepath)}")
        df = load_file(filepath)
        if df is not None:
            df = clean_dataframe(df, dataset_name)
            datasets[dataset_name] = df
        else:
            print(f"  FAILED to load {dataset_name}")
    
    return datasets


def save_processed(datasets: Dict[str, pd.DataFrame], directory: Optional[str] = None):
    """Save cleaned datasets to processed directory."""
    if directory is None:
        directory = DATA_PROCESSED_DIR
    
    os.makedirs(directory, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for name, df in datasets.items():
        filepath = os.path.join(directory, f"{name}_{timestamp}.parquet")
        df.to_parquet(filepath, index=False)
        print(f"Saved processed {name}: {filepath}")
    
    print(f"\nAll processed data saved to: {directory}")


def run_etl(directory: Optional[str] = None) -> Dict[str, pd.DataFrame]:
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