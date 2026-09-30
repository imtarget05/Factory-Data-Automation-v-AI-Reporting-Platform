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

from app.data_contracts.schemas import DATASET_MODELS
from app.utils.config import DATA_PROCESSED_DIR, DATA_RAW_DIR
from app.utils.logging_config import get_logger, log_event

# Measure columns that must be numeric for KPI math. Must stay in sync with
# app/data_contracts/schemas.py (Phase 2). Coerced with errors="coerce" so a
# stray text cell becomes NaN (then median-filled) instead of poisoning the
# whole column to str dtype and crashing groupby().mean() at startup.
NUMERIC_COLUMNS = frozenset(
    {
        "Target_Qty",
        "Actual_Qty",
        "Good_Qty",
        "Reject_Qty",
        "Cycle_Time_sec",
        "Stock_Qty",
        "Incoming_Qty",
        "Outgoing_Qty",
        "Reorder_Point",
        "Max_Capacity",
        "Unit_Price",
        "Defect_Count",
        "Inspected_Qty",
        "Speed_RPM",
        "Temperature_C",
        "Vibration_mm",
        "Power_Usage_pct",
        "Downtime_min",
        "Hours_Worked",
        "Units_Produced",
        "Defects_Caused",
        "Overtime_hrs",
    }
)

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

    # Coerce known measure columns to numeric FIRST. A single blank cell makes
    # pandas read the whole column as object/str, after which median-fill,
    # clip(lower=0) and downstream mean() all break (lifespan crash). Mirrors
    # the Phase-2 Data Contracts (app/data_contracts/schemas.py).
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Remove duplicates — deliberately BEFORE fills/clip, on the coerced frame:
    # dedup-on-raw first, so median-fill and .clip(lower=0) can never merge
    # distinct rows (-5 vs -1 becoming the same 0, the seeded idempotency
    # failure: 30 rows -> 29). reset_index keeps downstream positional drops
    # (.drop(index=...), e.g. the contract gate) honest.
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
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
    # include=["object", "string"] (not bare "object"): pandas 3 stores text as
    # "str" dtype and a bare "object" selector raises a Pandas4Warning there.
    for col in df.select_dtypes(include=["object", "string"]).columns:
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

    # No second dedup after clipping on purpose: two distinct rows that clip to
    # the same values stay distinct records. Double-counting dirty rows is the
    # caller's choice to quarantine (see apply_contract_gate), not the cleaner's.
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
            # Validate against the Phase-2 contracts BEFORE cleaning. The contract
            # is "contracts REJECT, cleaning FILLS": a row that violates a
            # hard rule (negative qty, future date, reject > actual) is written
            # to the quarantine DLQ and dropped, never silently imputed. Without
            # this step a typo silently skews OEE and Yield and looks like a real
            # production problem.
            df = apply_contract_gate(df, dataset_name, filepath)
            df = clean_dataframe(df, dataset_name)
            datasets[dataset_name] = df
        else:
            log_event(
                logger, "load_failed", level=logging.ERROR, component="etl", dataset=dataset_name
            )

    log_event(logger, "etl_complete", component="etl", datasets_loaded=list(datasets.keys()))
    return datasets


class ContractGateUnavailable(RuntimeError):  # noqa: N818 - intentional public API name (raised + caught by name in tests/callers)
    """The contract layer could not be evaluated, so no row can be trusted.

    P0-03. This exists to make one distinction impossible to get wrong:

    * a **business validation failure** (a row breaks a rule) is data, and is
      carried in a :class:`ValidationReport` so the caller can quarantine that
      row and keep the rest of the file;
    * a **validator implementation failure** (pydantic changed an API, a
      contract bug, a broken import) means the rules were never applied at all.
      Every row is *unknown*, and unknown is not approved.

    The pre-fix code caught ``Exception`` and returned the input frame
    unchanged, which silently converted the second case into the first: rows
    that no contract had ever checked were passed downstream as validated, and
    reached OEE / Yield / scrap-rate arithmetic. That is a data-correctness
    defect, not an availability trade-off.

    Raising here fails the job. That is deliberate and is the opposite of the
    old behaviour: an unvalidated KPI is worse than a failed run, because a
    failed run is visible and an unvalidated KPI is not.
    """


def apply_contract_gate(
    df: pd.DataFrame,
    dataset_name: str,
    filepath: str = "",
    quarantine_path: Optional[str] = None,
) -> pd.DataFrame:
    """Drop contract-violating rows, recording each one to the quarantine DLQ.

    Validation runs on the DataFrame that is about to enter KPI math, so the
    row indexes in the quarantine file match the rows actually removed.

    Fails CLOSED (P0-03). If the validator itself errors -- unknown dataset
    in the model registry, a pydantic API change, a contract bug -- the rules
    were never applied, so no row can be called valid. This raises
    :class:`ContractGateUnavailable` rather than returning the frame.

    The previous behaviour was the opposite, and this comment records why it
    was wrong rather than deleting it. It read: *"Fails open on purpose: if the
    validator itself errors, the pipeline logs it and returns the frame
    unchanged rather than discarding a whole file of good production data. A
    validator crash must not look like a total data outage."*

    The concern about discarding good data is legitimate, but it was addressed
    at the wrong level. Losing one file is a visible, recoverable outage.
    Silently accepting rows no contract checked is an invisible one: OEE,
    Yield and scrap rate are all computed over records that were never
    validated, and nothing downstream can tell. Genuine per-row violations
    still quarantine rather than abort, so a single typo still does not throw
    away a whole file -- that is the case the original comment was reaching
    for, and it is handled by the ValidationReport path, not here.
    """
    try:
        from app.data_contracts import infer_dataset, validate_rows
        from app.etl.quarantine import (
            rejected_row_indices,
            write_quarantine,
        )

        try:
            dataset = infer_dataset(os.path.basename(filepath)) if filepath else dataset_name
        except ValueError:
            dataset = dataset_name
        if dataset not in DATASET_MODELS:
            log_event(
                logger,
                "contract_skip",
                level=logging.WARNING,
                component="etl",
                dataset=dataset_name,
                reason="no_contract",
            )
            return df

        report = validate_rows(dataset, df.to_dict("records"))
        if not report.violations:
            return df

        # Map contract row positions back to DataFrame index labels before
        # dropping: reset_index() would renumber, and a duplicate/filtered index
        # would otherwise make .drop() remove the wrong rows.
        bad_positions = sorted(rejected_row_indices(report.violations))
        written = write_quarantine(
            report.violations,
            dataset=dataset,
            source_file=filepath or f"{dataset_name}.csv",
            **({"path": quarantine_path} if quarantine_path else {}),
        )
        clean_df = df.reset_index(drop=True).drop(index=bad_positions, errors="ignore")
        log_event(
            logger,
            "rows_quarantined",
            level=logging.WARNING,
            component="etl",
            dataset=dataset,
            rejected_rows=len(bad_positions),
            violation_records=len(report.violations),
            written=written,
            remaining=len(clean_df),
        )
        return clean_df
    except Exception as exc:
        # P0-03: this used to `return df`, i.e. accept every row unvalidated.
        # A gate that cannot run has not passed -- it has not run. Fail the job
        # so the rows are never used, and keep the original exception as
        # __cause__ so the operator sees the real cause.
        log_event(
            logger,
            "contract_gate_unavailable",
            level=logging.CRITICAL,
            component="etl",
            dataset=dataset_name,
            error=f"{type(exc).__name__}: {exc}",
            action="failing_closed",
            rows_rejected=len(df),
        )
        raise ContractGateUnavailable(
            f"contract validation could not be evaluated for dataset "
            f"{dataset_name!r}; refusing to pass {len(df)} unvalidated row(s) "
            f"downstream ({type(exc).__name__}: {exc})"
        ) from exc


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
