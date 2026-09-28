"""Tests for KPI Engine."""

import os
import sys

import pytest

pandas = pytest.importorskip("pandas", reason="pandas required (CI installs requirements.txt)")
pd = pandas

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.etl.kpi_engine import (  # noqa: E402
    calculate_daily_production,
    calculate_defect_analysis,
    calculate_inventory_kpi,
    calculate_machine_utilization,
    calculate_oee,
    calculate_worker_productivity,
)


class TestDailyProduction:
    def test_empty_input(self):
        result = calculate_daily_production(None)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_calculates_achievement(self):
        df = pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-01"],
                "Target_Qty": [100, 200],
                "Actual_Qty": [95, 190],
                "Good_Qty": [90, 180],
                "Reject_Qty": [5, 10],
                "Cycle_Time_sec": [30.0, 35.0],
            }
        )
        result = calculate_daily_production(df)
        assert not result.empty
        assert "Achievement_Rate_pct" in result.columns
        assert "Reject_Rate_pct" in result.columns
        assert "Yield_pct" in result.columns


class TestOEE:
    def test_empty_input(self):
        result = calculate_oee(None, None)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_oee_components(self):
        prod = pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-01"],
                "Target_Qty": [100, 200],
                "Actual_Qty": [95, 190],
                "Good_Qty": [90, 180],
                "Reject_Qty": [5, 10],
                "Cycle_Time_sec": [30.0, 35.0],
            }
        )
        mach = pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-01"],
                "Machine_ID": ["M-01", "M-02"],
                "Status": ["Running", "Running"],
                "Downtime_min": [5, 10],
                "Temperature_C": [70.0, 75.0],
                "Vibration_mm": [1.0, 1.5],
                "Power_Usage_pct": [80.0, 85.0],
                "Line": ["Line_1", "Line_2"],
            }
        )
        result = calculate_oee(prod, mach)
        assert not result.empty
        assert "OEE_pct" in result.columns
        assert "Availability_pct" in result.columns
        assert "Performance_pct" in result.columns
        assert "Quality_pct" in result.columns


class TestMachineUtilization:
    def test_empty_input(self):
        result = calculate_machine_utilization(None)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_utilization_rate(self):
        df = pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-01", "2026-01-01"],
                "Machine_ID": ["M-01", "M-01", "M-01"],
                "Status": ["Running", "Running", "Idle"],
                "Downtime_min": [0, 0, 0],
                "Temperature_C": [70.0, 72.0, 50.0],
                "Vibration_mm": [1.0, 1.1, 0.3],
                "Power_Usage_pct": [80.0, 82.0, 10.0],
                "Line": ["Line_1", "Line_1", "Line_1"],
            }
        )
        result = calculate_machine_utilization(df)
        assert not result.empty
        assert "Utilization_pct" in result.columns
        # 2 out of 3 readings are Running → ~66.7%
        assert result["Utilization_pct"].iloc[0] == 66.67


class TestInventoryKPI:
    def test_empty_input(self):
        result = calculate_inventory_kpi(None)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_stock_value(self):
        df = pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-01"],
                "Product": ["Shoe A", "Shoe B"],
                "Stock_Qty": [100, 200],
                "Incoming_Qty": [50, 30],
                "Outgoing_Qty": [20, 40],
                "Reorder_Point": [50, 100],
                "Max_Capacity": [500, 1000],
                "Unit_Price": [20.0, 30.0],
                "Supplier": ["A", "B"],
            }
        )
        result = calculate_inventory_kpi(df)
        assert not result.empty
        assert "Stock_Value" in result.columns
        assert "Total_Stock" in result.columns


class TestDefectAnalysis:
    def test_empty_input(self):
        result = calculate_defect_analysis(None)
        assert isinstance(result, dict)

    def test_defect_types(self):
        df = pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-01", "2026-01-01"],
                "Product": ["Shoe A", "Shoe B", "Shoe A"],
                "Line": ["Line_1", "Line_2", "Line_1"],
                "Defect_Type": ["Scratch", "Color", "Scratch"],
                "Defect_Count": [5, 3, 2],
                "Inspected_Qty": [100, 100, 100],
                "Severity": ["Minor", "Major", "Minor"],
                "Inspector_ID": ["E001", "E002", "E001"],
            }
        )
        result = calculate_defect_analysis(df)
        assert "by_type" in result
        assert "by_severity" in result
        assert "daily" in result


class TestWorkerProductivity:
    def test_empty_input(self):
        result = calculate_worker_productivity(None)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_units_per_hour(self):
        df = pd.DataFrame(
            {
                "Date": ["2026-01-01"],
                "Worker_ID": ["EMP_0001"],
                "Line": ["Line_1"],
                "Shift": ["Morning"],
                "Hours_Worked": [8.0],
                "Units_Produced": [80],
                "Defects_Caused": [2],
                "Attendance": ["Present"],
                "Overtime_hrs": [0.5],
            }
        )
        result = calculate_worker_productivity(df)
        assert not result.empty
        assert "Units_per_Hour" in result.columns
        assert result["Units_per_Hour"].iloc[0] == 10.0  # 80/8
