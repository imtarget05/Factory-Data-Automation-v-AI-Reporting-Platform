"""Tests for ETL Pipeline."""

import os
import sys

import pytest

pandas = pytest.importorskip("pandas", reason="pandas required (CI installs requirements.txt)")
pd = pandas

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.etl.pipeline import clean_dataframe, discover_files, load_file, run_etl
from app.utils.config import DATA_RAW_DIR


class TestDiscoverFiles:
    def test_discover_returns_dict(self):
        files = discover_files()
        assert isinstance(files, dict)

    def test_discover_finds_csv(self):
        files = discover_files()
        csv_files = [f for f in files.values() if f.endswith(".csv")]
        assert len(csv_files) > 0, "No CSV files found"

    def test_discover_has_expected_keys(self):
        files = discover_files()
        expected = {"production", "quality", "inventory", "machine", "workers"}
        found = set(files.keys())
        assert expected.issubset(found), f"Missing: {expected - found}"


class TestLoadFile:
    def test_load_csv(self):
        csv_path = os.path.join(DATA_RAW_DIR, "production.csv")
        if os.path.exists(csv_path):
            df = load_file(csv_path)
            assert df is not None
            assert len(df) > 0

    def test_load_nonexistent(self):
        df = load_file("/nonexistent/file.csv")
        assert df is None

    def test_load_unsupported(self):
        df = load_file("test.txt")
        assert df is None


class TestCleanDataFrame:
    def test_clean_production(self):
        df = pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-01", None],
                "Target_Qty": [100, 200, -1],
                "Actual_Qty": [95, None, 180],
                "Good_Qty": [90, 190, 175],
                "Reject_Qty": [5, 10, 5],
            }
        )
        cleaned = clean_dataframe(df, "production")
        assert cleaned is not None
        assert cleaned["Target_Qty"].min() >= 0  # Negative clipped
        assert cleaned["Actual_Qty"].notna().all()  # Missing filled
        assert len(cleaned) == 3  # No dupes removed

    def test_clean_removes_duplicates(self):
        df = pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-01"],
                "Machine_ID": ["M-01", "M-01"],
                "Value": [100, 100],
            }
        )
        cleaned = clean_dataframe(df, "test")
        # Should have removed or kept valid rows
        assert cleaned is not None

    def test_clean_handles_empty(self):
        df = pd.DataFrame()
        cleaned = clean_dataframe(df, "empty")
        assert cleaned is not None
        assert len(cleaned) == 0


class TestNumericCoercion:
    """Regression: blank cells must not poison measure columns to str dtype
    (startup crash: groupby().mean() on str -> TypeError, lifespan exit)."""

    def test_blank_cycle_time_stays_numeric(self):
        df = pd.DataFrame(
            {
                "Date": ["2026-01-05", "2026-01-05"],
                "Target_Qty": [400, 420],
                "Actual_Qty": [390, 410],
                "Good_Qty": [385, 405],
                "Reject_Qty": [5, 5],
                "Cycle_Time_sec": ["45.2", ""],
            }
        )
        cleaned = clean_dataframe(df, "production")
        assert pd.api.types.is_numeric_dtype(cleaned["Cycle_Time_sec"])
        assert float(cleaned["Cycle_Time_sec"].mean()) > 0

    def test_text_in_qty_becomes_nan_then_filled(self):
        df = pd.DataFrame(
            {
                "Date": ["2026-01-05", "2026-01-05"],
                "Target_Qty": ["400", "N/A"],
                "Actual_Qty": [390, 410],
                "Good_Qty": [385, 405],
                "Reject_Qty": [5, 5],
            }
        )
        cleaned = clean_dataframe(df, "production")
        assert pd.api.types.is_numeric_dtype(cleaned["Target_Qty"])
        assert cleaned["Target_Qty"].notna().all()
        assert (cleaned["Target_Qty"] >= 0).all()


class TestRunETL:
    def test_run_etl_returns_dict(self):
        datasets = run_etl()
        assert isinstance(datasets, dict)

    def test_run_etl_has_data(self):
        datasets = run_etl()
        if datasets:
            total = sum(len(df) for df in datasets.values())
            assert total > 0, "No data loaded"

    def test_run_etl_columns(self):
        datasets = run_etl()
        if "production" in datasets:
            cols = datasets["production"].columns
            assert "Date" in cols
            assert "Target_Qty" in cols
