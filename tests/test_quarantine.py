"""Tests for the contract gate + quarantine DLQ wired into the ETL.

The bug this guards against
---------------------------
Phase-2 data contracts shipped with 21 passing tests but were never called by
the pipeline. A row with ``Target_Qty = -50`` or a future-dated shift flowed
straight into the KPI math, so a data-entry typo was indistinguishable from a
real production problem in the OEE/Yield report.

These tests assert the gate is actually *in the execution path*, that rejected
rows are recorded (not silently dropped), and — the security point — that
attacker-controlled cell values cannot re-arm as formulas when an operator
opens the quarantine file in Excel.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.etl.quarantine import (  # noqa: E402
    QUARANTINE_COLUMNS,
    dedupe_violations,
    quarantine_summary,
    rejected_row_indices,
    sanitize_quarantine_cell,
    write_quarantine,
)

pd = pytest.importorskip("pandas")


@pytest.fixture()
def qpath(tmp_path):
    return str(tmp_path / "quarantine" / "corrupt_records.csv")


def _read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --- sanitizer: security-critical -------------------------------------------


class TestSanitizeQuarantineCell:
    @pytest.mark.parametrize(
        "payload",
        [
            "=1+1",
            "=cmd|'/c calc'!A0",
            "@SUM(1+1)",
            "+2+2",
            "-2+3",
            '  =HYPERLINK("http://evil","x")',
            "\t=CMD()",
        ],
    )
    def test_formula_payloads_are_neutralized(self, payload):
        safe = sanitize_quarantine_cell(payload)
        # The first character the spreadsheet sees must be the guard quote, so
        # the cell is read as text. (Stripping that quote again would of course
        # reveal the original payload — that is the point, not a failure.)
        assert safe.startswith("'"), f"payload not neutralized: {payload!r}"

    def test_content_is_preserved_for_audit(self):
        """Quarantining must not silently destroy evidence."""
        safe = sanitize_quarantine_cell("=cmd|'/c calc'!A0")
        assert "cmd" in safe and "calc" in safe

    @pytest.mark.parametrize("benign", ["M-01", "L1", "120", "98.5", "Ca đêm", "2026-01-05", ""])
    def test_benign_values_are_untouched(self, benign):
        assert sanitize_quarantine_cell(benign) == benign

    def test_none_maps_to_empty(self):
        assert sanitize_quarantine_cell(None) == ""

    def test_negative_numbers_follow_the_shared_repo_contract(self):
        """Deliberately consistent with tests/test_csv_injection.py.

        That contract stringifies first, so a negative quantity is quoted too.
        Being *more* permissive here would create two different injection guards
        in one repo, and the audit column is read as text anyway.
        """
        assert sanitize_quarantine_cell(-5) == "'-5"
        assert sanitize_quarantine_cell(3.5) == "3.5"


# --- dedupe / row selection --------------------------------------------------


class TestDedupeViolations:
    def test_same_row_and_field_collapses_to_one(self):
        violations = [
            {"row_index": 0, "field": "Actual_Qty", "value": -5, "rule": "gte"},
            {"row_index": 0, "field": "Actual_Qty", "value": -5, "rule": "gte"},
        ]
        assert len(dedupe_violations(violations)) == 1

    def test_different_fields_are_kept(self):
        violations = [
            {"row_index": 0, "field": "Target_Qty", "value": -5, "rule": "gte"},
            {"row_index": 0, "field": "Actual_Qty", "value": -5, "rule": "gte"},
        ]
        assert len(dedupe_violations(violations)) == 2

    def test_different_rows_are_kept(self):
        violations = [
            {"row_index": 0, "field": "Target_Qty", "value": -5, "rule": "gte"},
            {"row_index": 1, "field": "Target_Qty", "value": -7, "rule": "gte"},
        ]
        assert len(dedupe_violations(violations)) == 2

    def test_rejected_indices_deduped(self):
        violations = [{"row_index": 3, "field": "a"}, {"row_index": 3, "field": "b"}]
        assert rejected_row_indices(violations) == {3}


class TestWriteQuarantine:
    def test_writes_header_and_rows(self, qpath):
        n = write_quarantine(
            [{"row_index": 0, "field": "Target_Qty", "value": -5, "rule": "gte"}],
            dataset="production",
            source_file="/data/raw/production.csv",
            path=qpath,
        )
        assert n == 1
        rows = _read(qpath)
        assert len(rows) == 1
        assert list(rows[0]) == QUARANTINE_COLUMNS
        assert rows[0]["dataset"] == "production"
        assert rows[0]["source_file"] == "production.csv"  # basename only

    def test_empty_violations_creates_no_file(self, qpath):
        assert write_quarantine([], dataset="production", path=qpath) == 0
        assert not os.path.exists(qpath)

    def test_appends_across_runs_without_duplicating_header(self, qpath):
        for i in range(3):
            write_quarantine(
                [{"row_index": i, "field": "Target_Qty", "value": -i, "rule": "gte"}],
                dataset="production",
                path=qpath,
            )
        rows = _read(qpath)
        assert len(rows) == 3
        with open(qpath, encoding="utf-8") as fh:
            assert sum(1 for line in fh if line.startswith("quarantined_at")) == 1

    def test_formula_payload_in_value_is_sanitized_on_disk(self, qpath):
        write_quarantine(
            [{"row_index": 0, "field": "Supplier", "value": "=cmd|'/c calc'!A0", "rule": "x"}],
            dataset="inventory",
            path=qpath,
        )
        row = _read(qpath)[0]
        assert row["value"].startswith("'")
        assert not row["value"].lstrip(" \t").startswith("=")

    def test_unwritable_path_does_not_raise(self):
        # A full disk / read-only mount must not abort an ETL that already
        # cleaned good data.
        assert (
            write_quarantine(
                [{"row_index": 0, "field": "a", "value": 1, "rule": "r"}],
                dataset="production",
                path="/proc/not-writable/x.csv",
            )
            == 0
        )

    def test_summary_counts_by_dataset(self, qpath):
        write_quarantine(
            [{"row_index": 0, "field": "a", "value": 1, "rule": "r"}],
            dataset="production",
            path=qpath,
        )
        write_quarantine(
            [{"row_index": 1, "field": "a", "value": 1, "rule": "r"}], dataset="quality", path=qpath
        )
        write_quarantine(
            [{"row_index": 2, "field": "a", "value": 1, "rule": "r"}], dataset="quality", path=qpath
        )
        assert quarantine_summary(qpath) == {"production": 1, "quality": 2}

    def test_summary_of_missing_file_is_empty(self, qpath):
        assert quarantine_summary(qpath) == {}


class TestContractGateInPipeline:
    """The gate must run in the real ETL path, not just in isolation."""

    @staticmethod
    def _row(target, reject):
        return {
            "Date": "2026-01-05",
            "Line": "L1",
            "Shift": "S1",
            "Product": "P1",
            "Machine_ID": "M-01",
            "Worker_ID": "W-1",
            "Target_Qty": target,
            "Actual_Qty": 90,
            "Good_Qty": 85,
            "Reject_Qty": reject,
            "Cycle_Time_sec": 30.0,
            "Created_At": "2026-01-05T07:00:00",
        }

    @classmethod
    def _frame(cls):
        return pd.DataFrame(
            [
                cls._row(100, 5),  # valid
                cls._row(-50, 5),  # negative target
                cls._row(100, 999),  # reject > actual: internally inconsistent
            ]
        )

    def test_bad_rows_are_dropped_not_imputed(self, qpath):
        from app.etl.pipeline import apply_contract_gate

        out = apply_contract_gate(
            self._frame(), "production", "production.csv", quarantine_path=qpath
        )
        # Rows 1 and 2 violate hard rules and must be GONE, not clipped to 0 —
        # clipping would invent a plausible-looking production record.
        assert len(out) == 1
        assert out.iloc[0]["Target_Qty"] == 100

    def test_dropped_rows_are_recorded(self, qpath):
        from app.etl.pipeline import apply_contract_gate

        apply_contract_gate(self._frame(), "production", "production.csv", quarantine_path=qpath)
        rows = _read(qpath)
        assert {r["row_index"] for r in rows} == {"1", "2"}
        assert all(r["dataset"] == "production" for r in rows)

    def test_gate_is_idempotent(self, qpath):
        """A second pass must find nothing left to reject."""
        from app.etl.pipeline import apply_contract_gate

        out = apply_contract_gate(
            self._frame(), "production", "production.csv", quarantine_path=qpath
        )
        before = os.path.getsize(qpath)
        apply_contract_gate(out, "production", "production.csv", quarantine_path=qpath)
        assert os.path.getsize(qpath) == before

    def test_valid_frame_is_untouched(self, qpath):
        from app.etl.pipeline import apply_contract_gate

        good = self._frame().iloc[[0]].copy()
        out = apply_contract_gate(good, "production", "production.csv", quarantine_path=qpath)
        assert len(out) == 1
        assert not os.path.exists(qpath)

    def test_unknown_dataset_fails_open(self, qpath):
        """No contract for this dataset must not discard good data."""
        from app.etl.pipeline import apply_contract_gate

        df = self._frame()
        out = apply_contract_gate(df, "nonexistent", "nonexistent.csv", quarantine_path=qpath)
        assert len(out) == len(df)

    def test_gate_runs_in_load_and_clean_all(self, tmp_path):
        """End-to-end: the real ETL entry point must invoke the gate."""
        from app.etl import pipeline

        raw = tmp_path / "raw"
        raw.mkdir()
        self._frame().iloc[[0]].to_csv(raw / "production.csv", index=False)

        q = str(tmp_path / "q.csv")
        seen = []
        original = pipeline.apply_contract_gate

        def spy(df, dataset_name, filepath="", quarantine_path=None):
            seen.append(dataset_name)
            return original(df, dataset_name, filepath, quarantine_path or q)

        pipeline.apply_contract_gate = spy
        try:
            pipeline.load_and_clean_all(str(raw))
        finally:
            pipeline.apply_contract_gate = original
        assert "production" in seen

    def test_end_to_end_rejects_the_bad_file(self, tmp_path):
        from app.etl import pipeline

        raw = tmp_path / "raw"
        raw.mkdir()
        self._frame().iloc[[1]].to_csv(raw / "production.csv", index=False)
        out = pipeline.load_and_clean_all(str(raw))
        assert "production" in out
        assert len(out["production"]) == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
