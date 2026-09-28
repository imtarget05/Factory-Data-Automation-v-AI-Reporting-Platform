"""Phase-2 data-contract tests (stdlib + pydantic only; no pandas/numpy).

Covers every rule in app/data_contracts/schemas.py: non-negative
quantities, Reject_Qty <= Actual_Qty, Defect_Count <= Inspected_Qty,
Hours_Worked 0..24, ISO Date not in the future, numeric-string coercion,
blank rejection, extra-column tolerance, quarantine separation, real
data/raw/*.csv parsing, and unknown-dataset errors.
"""

from pathlib import Path

import pytest

from app.data_contracts import validate_csv, validate_rows

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"


def _production_row(**overrides):
    row = {
        "Date": "2026-01-05",
        "Line": "L1",
        "Shift": "Shift-1",
        "Product": "SKU-A",
        "Machine_ID": "M-01",
        "Worker_ID": "W-001",
        "Target_Qty": 400,
        "Actual_Qty": 390,
        "Good_Qty": 385,
        "Reject_Qty": 5,
        "Cycle_Time_sec": 60.5,
        "Created_At": "2026-01-05T07:00:00",
    }
    row.update(overrides)
    return row


def _quality_row(**overrides):
    row = {
        "Date": "2026-01-05",
        "Product": "SKU-A",
        "Line": "L1",
        "Defect_Type": "Scratch",
        "Defect_Count": 3,
        "Inspected_Qty": 200,
        "Severity": "Minor",
        "Inspector_ID": "W-001",
        "Created_At": "2026-01-05T08:00:00",
    }
    row.update(overrides)
    return row


def _inventory_row(**overrides):
    row = {
        "Date": "2026-01-05",
        "Product": "SKU-A",
        "Stock_Qty": 500,
        "Incoming_Qty": 15,
        "Outgoing_Qty": 20,
        "Reorder_Point": 150,
        "Max_Capacity": 2000,
        "Unit_Price": 25.5,
        "Supplier": "ACME",
        "Created_At": "2026-01-05T08:00:00",
    }
    row.update(overrides)
    return row


def _machine_row(**overrides):
    row = {
        "Date": "2026-01-05",
        "Machine_ID": "M-01",
        "Status": "Running",
        "Speed_RPM": 92.5,
        "Temperature_C": 75.0,
        "Vibration_mm": 1.75,
        "Power_Usage_pct": 82.5,
        "Downtime_min": 0,
        "Line": "L1",
        "Created_At": "2026-01-05T08:00:00",
    }
    row.update(overrides)
    return row


def _worker_row(**overrides):
    row = {
        "Date": "2026-01-05",
        "Worker_ID": "W-001",
        "Line": "L1",
        "Shift": "Shift-1",
        "Hours_Worked": 8.0,
        "Units_Produced": 80,
        "Defects_Caused": 1,
        "Attendance": "Present",
        "Overtime_hrs": 0.5,
        "Created_At": "2026-01-05T08:00:00",
    }
    row.update(overrides)
    return row


_VALID = {
    "production": _production_row,
    "quality": _quality_row,
    "inventory": _inventory_row,
    "machine": _machine_row,
    "workers": _worker_row,
}


def test_valid_rows_pass_for_all_datasets():
    for dataset, factory in _VALID.items():
        report = validate_rows(dataset, [factory()])
        assert len(report.passed) == 1, f"{dataset}: {report.violations}"
        assert report.violations == []


def test_negative_target_qty_is_violation():
    report = validate_rows("production", [_production_row(Target_Qty=-400)])
    assert report.passed == []
    assert any(v["field"] == "Target_Qty" for v in report.violations)


def test_negative_actual_good_reject_qty_are_violations():
    for field in ("Actual_Qty", "Good_Qty", "Reject_Qty"):
        report = validate_rows("production", [_production_row(**{field: -1})])
        assert report.passed == [], field
        assert any(v["field"] == field for v in report.violations), field


def test_reject_qty_above_actual_qty_is_violation():
    report = validate_rows(
        "production", [_production_row(Actual_Qty=100, Good_Qty=90, Reject_Qty=101)]
    )
    assert report.passed == []
    assert len(report.violations) == 1
    assert report.violations[0]["value"]["Reject_Qty"] == 101


def test_future_date_is_violation_on_all_datasets():
    for dataset, factory in _VALID.items():
        report = validate_rows(dataset, [factory(Date="2099-01-01")])
        assert report.passed == [], dataset
        assert any(v["field"] == "Date" for v in report.violations), dataset


def test_malformed_date_is_violation():
    report = validate_rows("production", [_production_row(Date="not-a-date")])
    assert report.passed == []
    assert any(v["field"] == "Date" for v in report.violations)


def test_text_in_number_cell_is_violation():
    report = validate_rows("production", [_production_row(Target_Qty="abc")])
    assert report.passed == []
    assert any(v["field"] == "Target_Qty" for v in report.violations)


def test_blank_and_none_required_fields_are_violations():
    for bad in ("", "   ", None):
        report = validate_rows("production", [_production_row(Line=bad)])
        assert report.passed == [], repr(bad)
        assert any(v["field"] == "Line" for v in report.violations), repr(bad)
    report = validate_rows("production", [_production_row(Target_Qty="")])
    assert report.passed == []
    assert any(v["field"] == "Target_Qty" for v in report.violations)


def test_missing_mandatory_columns_are_violations_not_crash():
    """FDA-004: a row missing mandatory columns must yield violations, never raise."""
    row = _production_row()
    for missing in ("Actual_Qty", "Good_Qty", "Machine_ID"):
        partial = {k: v for k, v in row.items() if k != missing}
        report = validate_rows("production", [partial])
        assert report.passed == [], missing
        assert any(
            v["field"] == missing and "required" in v["rule"].lower() for v in report.violations
        ), (missing, report.violations)


def test_defect_count_above_inspected_qty_is_violation():
    report = validate_rows("quality", [_quality_row(Defect_Count=250, Inspected_Qty=200)])
    assert report.passed == []
    assert len(report.violations) == 1


def test_negative_defect_or_inspected_qty_is_violation():
    for field in ("Defect_Count", "Inspected_Qty"):
        report = validate_rows("quality", [_quality_row(**{field: -2})])
        assert report.passed == [], field
        assert any(v["field"] == field for v in report.violations), field


def test_hours_worked_above_24_is_violation():
    report = validate_rows("workers", [_worker_row(Hours_Worked=25)])
    assert report.passed == []
    assert any(v["field"] == "Hours_Worked" for v in report.violations)
    # Boundaries: 0 and 24 are legal, negative is not.
    assert len(validate_rows("workers", [_worker_row(Hours_Worked=24)]).passed) == 1
    assert len(validate_rows("workers", [_worker_row(Hours_Worked=0)]).passed) == 1
    bad = validate_rows("workers", [_worker_row(Hours_Worked=-1)])
    assert bad.passed == []


def test_negative_stock_qty_is_violation():
    report = validate_rows("inventory", [_inventory_row(Stock_Qty=-50)])
    assert report.passed == []
    assert any(v["field"] == "Stock_Qty" for v in report.violations)


def test_negative_incoming_or_outgoing_qty_is_violation():
    for field in ("Incoming_Qty", "Outgoing_Qty"):
        report = validate_rows("inventory", [_inventory_row(**{field: -3})])
        assert report.passed == [], field
        assert any(v["field"] == field for v in report.violations), field


def test_numeric_strings_are_coerced():
    row = _production_row(
        Target_Qty="42",
        Actual_Qty="40",
        Good_Qty="39",
        Reject_Qty="1",
        Cycle_Time_sec="60.5",
    )
    report = validate_rows("production", [row])
    assert report.violations == []
    coerced = report.passed[0]
    assert coerced["Target_Qty"] == 42
    assert isinstance(coerced["Target_Qty"], int)
    assert coerced["Cycle_Time_sec"] == 60.5


def test_extra_columns_are_ignored_not_violations():
    row = _production_row()
    row["Brand_New_Column"] = "whatever"
    report = validate_rows("production", [row])
    assert report.violations == []
    assert len(report.passed) == 1
    assert "Brand_New_Column" not in report.passed[0]


def test_quarantine_separation_mixed_batch_counts_exact():
    rows = [
        _production_row(),  # 0: pass
        _production_row(Target_Qty=-5),  # 1: 1 violation
        _production_row(),  # 2: pass
        _production_row(Actual_Qty=100, Good_Qty=90, Reject_Qty=101),  # 3: 1 violation
        _production_row(Date="2099-06-01"),  # 4: 1 violation
    ]
    report = validate_rows("production", rows)
    assert len(report.passed) == 2
    assert len(report.violations) == 3
    assert sorted(v["row_index"] for v in report.violations) == [1, 3, 4]


def test_violation_record_shape():
    report = validate_rows("production", [_production_row(Target_Qty=-1)])
    assert len(report.violations) == 1
    record = report.violations[0]
    assert set(record) == {"row_index", "field", "value", "rule"}
    assert record["row_index"] == 0
    assert record["field"] == "Target_Qty"
    assert record["value"] == -1
    assert isinstance(record["rule"], str) and record["rule"]


def test_validate_rows_never_raises_on_bad_data():
    bad_rows = [
        {},
        {"Date": None, "Target_Qty": None},
        {"Date": "2099-01-01", "Target_Qty": "abc", "Line": ""},
        {"Date": "2026-13-45", "Target_Qty": "1.5.2"},
    ]
    report = validate_rows("production", bad_rows)
    assert report.passed == []
    assert len(report.violations) >= len(bad_rows)


def test_validate_csv_on_real_raw_files_parses_without_crash():
    for dataset in ("production", "quality", "inventory", "machine", "workers"):
        path = RAW_DIR / f"{dataset}.csv"
        assert path.exists(), f"missing seed file {path}"
        report = validate_csv(str(path))
        # Violations are allowed (seed data is deliberately dirty) but every
        # one must be an enumerated record, never a crash.
        for v in report.violations:
            assert set(v) == {"row_index", "field", "value", "rule"}
        assert len(report.passed) + len({v["row_index"] for v in report.violations}) > 0


def test_validate_csv_explicit_dataset_and_unknown_dataset():
    path = RAW_DIR / "production.csv"
    report = validate_csv(str(path), dataset="production")
    assert isinstance(report.passed, list)
    with pytest.raises(ValueError):
        validate_rows("nonexistent", [_production_row()])
    with pytest.raises(ValueError):
        validate_csv(str(path), dataset="nonexistent")


def test_unknown_filename_and_missing_file_raise_value_error():
    with pytest.raises(ValueError):
        validate_csv(str(REPO_ROOT / "README.md"))
    with pytest.raises(ValueError):
        validate_csv(str(RAW_DIR / "does_not_exist.csv"))
