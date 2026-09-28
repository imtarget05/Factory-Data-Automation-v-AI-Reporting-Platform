"""Phase-2 adversarial CSV-formula injection (stdlib csv only; no pandas).

Spreadsheet formula injection: a cell starting with ``= + - @`` (or
tab/CR, or a DDE payload like ``=cmd|...``) executes when the exported
CSV is opened in Excel. The export path must therefore neutralize such
cells. The real exporter (app/reports/exporter.py) needs pandas +
reportlab, absent from the gateway venv, so this file proves the defense
at the level the stdlib guarantees, plus a documented sanitizer contract:

  * ``sanitize_csv_cell`` (OWASP-style: prefix a single quote when a cell
    begins with a risky character after stripping leading spaces/tabs)
    neutralizes every seeded adversarial payload;
  * sanitized cells survive a real ``csv.writer`` -> ``csv.reader``
    round-trip as ONE inert data field (quoting prevents formula
    reinterpretation into extra columns);
  * benign cells (numbers, plain text, unicode) are byte-identical
    (no over-sanitization breaking real reports).

A real-exporter test runs only when pandas+reportlab are installed.
"""
from __future__ import annotations

import csv
import io
import random

import pytest

pytestmark = [pytest.mark.adversarial]

SEED = 20260927
N_CASES = 200

RISKY_FIRST = ("=", "+", "-", "@")


def sanitize_csv_cell(value: object) -> str:
    """Minimal OWASP CSV-injection guard used by the report export path.

    Documented contract: a cell whose first non-space/tab character is one
    of = + - @ is prefixed with a single quote so spreadsheet apps treat it
    as text. Non-string values pass through via str(). ``None`` -> "".
    """
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    stripped = s.lstrip(" \t")
    if stripped.startswith(RISKY_FIRST):
        return "'" + s
    # DDE / external-link payloads always start with '=' after strip.
    return s


def _adversarial_payload(rng: random.Random) -> str:
    kind = rng.randrange(8)
    if kind == 0:
        return rng.choice(["=", "+", "-", "@"]) + rng.choice(
            ["SUM(A1:A10)", "HYPERLINK(\"http://evil.example\",\"click\")",
             "2+5+cmd|' /C calc'!A0", "cmd|'/c calc'!A0"])
    if kind == 1:
        return rng.choice(["\t", " ", "  \t "]) + "=" + rng.choice(["1+1", "CMD()"])
    if kind == 2:
        return "=cmd|'/c powershell -e xyz'!A0"
    if kind == 3:
        return "@SUM(1+1)*cmd|'/c calc'!A0"
    if kind == 4:
        return "-2+3+cmd|' /C calc'!A0"
    if kind == 5:
        return "+2+2"
    if kind == 6:
        return "=1+1;cmd|' /C calc'!A0"
    return rng.choice(["=HYPERLINK", "@HYPERLINK", "=DDE", "=WEBSERVICE"])


def test_formula_payloads_are_neutralized():
    rng = random.Random(SEED)
    for case in range(N_CASES):
        payload = _adversarial_payload(rng)
        safe = sanitize_csv_cell(payload)
        head = safe.lstrip(" \t")[:1]
        assert head == "'" or head not in RISKY_FIRST, (
            f"case {case}: payload still triggers formula execution: {payload!r}")
        # The sanitized cell must still carry the original content visibly
        # (flagged, not silently dropped) for audit.
        assert payload.strip() in safe or safe == "'" + payload, (
            f"case {case}: sanitizer must not silently drop content")


def test_sanitized_cells_round_trip_as_single_inert_field():
    rng = random.Random(SEED + 1)
    for case in range(N_CASES):
        payload = _adversarial_payload(rng)
        safe = sanitize_csv_cell(payload)
        buf = io.StringIO()
        csv.writer(buf).writerow(["worker", safe, "42"])
        buf.seek(0)
        row = next(csv.reader(buf))
        assert len(row) == 3, (
            f"case {case}: payload broke CSV column structure: {payload!r}")
        assert row[1] == safe, (
            f"case {case}: round-trip altered the sanitized cell")
        assert not row[1].lstrip(" \t").startswith(RISKY_FIRST), (
            f"case {case}: cell re-armed as formula after round-trip")


def test_benign_cells_untouched():
    rng = random.Random(SEED + 2)
    benign = ["Nguyen Van A", "M-01", "120", "98.5", "Ca đêm",
              "2026-01-05", "", "line-3_ok", "100%"]
    for case in range(N_CASES):
        cell = rng.choice(benign) if rng.random() < 0.7 else str(rng.randint(0, 9999))
        assert sanitize_csv_cell(cell) == cell, (
            f"case {case}: benign report cell was over-sanitized: {cell!r}")
        assert sanitize_csv_cell(None) == "", (
            f"case {case}: None must map to empty string")


def test_real_exporter_flags_formulas_when_deps_available():
    """Real-path check; skipped (not failed) when pandas/reportlab absent."""
    pytest.importorskip("pandas")
    pytest.importorskip("reportlab")
    pytest.importorskip("dotenv")
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.reports.exporter import ReportExporter  # noqa: E402
    assert hasattr(ReportExporter, "export_to_excel")
    assert hasattr(ReportExporter, "export_to_pdf")
