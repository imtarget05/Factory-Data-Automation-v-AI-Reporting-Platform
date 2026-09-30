"""Quarantine (DLQ) for rows rejected by the Phase-2 data contracts.

Why this exists
---------------
``app/data_contracts`` was built and tested (21 tests) but never wired into the
ETL that actually runs. Every bad row therefore flowed straight into the KPI
math, where a negative quantity or a future-dated shift silently skews OEE and
Yield — and nobody can tell a genuine production problem from a data-entry typo.

This module is the missing link: ``validate_csv`` reports violations, this
writes them to ``data/quarantine/corrupt_records.csv`` with enough context to
replay or fix the source file.

Two design points that are easy to get wrong
--------------------------------------------
1. **Violations are deduped per (row, field).** One bad row usually trips several
   rules (``Reject_Qty > Actual_Qty`` *and* ``Actual_Qty`` negative). Writing
   every violation would bury the row under near-duplicate lines and make the
   quarantine file useless for triage.
2. **Quarantined values are sanitized for spreadsheet formula injection.** The
   offending cell is attacker-controlled data lifted verbatim out of an uploaded
   file, and the quarantine file is opened in Excel by whoever triages it. A cell
   beginning ``=``/``+``/``-``/``@`` would execute on open. This reuses the exact
   OWASP contract the report export path documents in
   ``tests/test_csv_injection.py`` — prefix a single quote, never drop content,
   so the operator can still read what the bad value was.
"""

from __future__ import annotations

import csv
import os
import threading
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.utils.config import DATA_QUARANTINE_FILE

# First characters a spreadsheet app will evaluate as a formula.
RISKY_PREFIXES = ("=", "+", "-", "@")

QUARANTINE_COLUMNS = [
    "quarantined_at",
    "dataset",
    "source_file",
    "row_index",
    "field",
    "value",
    "rule",
]

# Appends from concurrent ETL runs must not interleave mid-row.
_write_lock = threading.Lock()

# Quarantine counts for the CURRENT ETL run only.
#
# The DLQ file is append-only, so counting its rows mixes every run that has
# ever happened into one number. Dividing that by a per-run `passed` count makes
# the rate climb on every run until it crosses the threshold and reporting is
# blocked forever, regardless of how clean the data is. The file stays the
# audit record; the gate gets run-scoped counters.
_run_lock = threading.Lock()
_run_counts: dict[str, int] = {}


def reset_run_quarantine() -> None:
    """Zero the run-scoped counters. Called at the start of an ETL run."""
    with _run_lock:
        _run_counts.clear()


def record_run_quarantine(dataset: str, rows: int) -> None:
    """Add rows quarantined for `dataset` during this run."""
    if rows <= 0:
        return
    with _run_lock:
        _run_counts[dataset] = _run_counts.get(dataset, 0) + int(rows)


def quarantine_run_summary() -> dict[str, int]:
    """Quarantined rows per dataset for the current ETL run.

    Empty dict means no ETL has run in this process, which is NOT the same as
    "nothing was quarantined". Callers must pass that state through as
    not-provided rather than substituting a zero.
    """
    with _run_lock:
        return dict(_run_counts)


def sanitize_quarantine_cell(value: Any) -> str:
    """Neutralize a CSV-formula payload without hiding its content.

    Mirrors the documented export-path contract in
    ``tests/test_csv_injection.py``: stringify, then prefix a single quote when
    the first non-space character is ``= + - @``. A negative number is therefore
    quoted too — being more permissive here would mean two different injection
    guards in one repo, and this column is read as text by an operator anyway.
    """
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    if s.lstrip(" \t").startswith(RISKY_PREFIXES):
        return "'" + s
    return s


def dedupe_violations(violations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse a row's repeated failures into one record per (row_index, field).

    Without this, a row failing four rules produces four near-identical lines and
    the operator cannot tell how many rows were actually rejected.
    """
    seen = set()
    unique: list[dict[str, Any]] = []
    for v in violations:
        key = (v.get("row_index"), v.get("field"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(v)
    return unique


def rejected_row_indices(violations: Iterable[dict[str, Any]]) -> set[int]:
    """Row indexes that must be dropped from the DataFrame before KPI math."""
    return {int(v["row_index"]) for v in violations if v.get("row_index") is not None}


def write_quarantine(
    violations: Iterable[dict[str, Any]],
    dataset: str,
    source_file: str = "",
    path: str = DATA_QUARANTINE_FILE,
) -> int:
    """Append rejected rows to the quarantine CSV. Returns rows written.

    Never raises: a full disk or a read-only mount must not abort an ETL run that
    has already cleaned good data. The caller logs the failure instead.
    """
    records = dedupe_violations(violations)
    if not records:
        return 0

    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        is_new = not os.path.exists(path) or os.path.getsize(path) == 0
        stamp = datetime.now().isoformat(timespec="seconds")
        record_run_quarantine(dataset, len(records))
        with _write_lock, open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if is_new:
                writer.writerow(QUARANTINE_COLUMNS)
            for v in records:
                writer.writerow(
                    [
                        stamp,
                        dataset,
                        os.path.basename(source_file),
                        v.get("row_index"),
                        sanitize_quarantine_cell(v.get("field")),
                        sanitize_quarantine_cell(v.get("value")),
                        sanitize_quarantine_cell(v.get("rule")),
                    ]
                )
        return len(records)
    except OSError:
        return 0


def quarantine_summary(path: str = DATA_QUARANTINE_FILE) -> dict[str, int]:
    """Cumulative quarantined rows per dataset across the whole DLQ file.

    This is the AUDIT view: it never shrinks, because the DLQ is append-only.
    Do NOT divide it by a per-run row count to get a rate -- see
    `quarantine_run_summary()` for the number the quality gate must use.
    """
    try:
        if not os.path.exists(path):
            return {}
        counts: dict[str, int] = {}
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                dataset = row.get("dataset") or "unknown"
                counts[dataset] = counts.get(dataset, 0) + 1
        return counts
    except OSError:
        return {}
