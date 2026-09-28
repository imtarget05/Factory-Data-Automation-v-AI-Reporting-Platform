# Defect Report — Factory Data Automation + AI Reporting

| ID | Severity | Title | Repro | Evidence | Status |
|---|---|---|---|---|---|
| DEF-FACT-001 | S3 (test-only) | `tests/test_csv_injection.py:125` called `sys.insert` instead of `sys.path.insert`. | `pytest -q tests/test_csv_injection.py` | `evidence/2026-09-27-per-file.log` | FIXED (verified by green run) |
| DEF-FACT-002 | P0 | Missing Pandas/Polars parity automated test suite (FDA-009). | Contract audit | `tests/test_polars_parity.py` added with 7 tests across synthetic, raw files & KPI output | FIXED 2026-09-28 (7/7 passed) |
| DEF-FACT-003 | P1 | Missing scale / huge input test suite (FDA-013). | Contract audit | `tests/test_scale_and_perf.py::test_fda_013_scale_10x_pipeline_survives` added (10x volume ~110k rows) | FIXED 2026-09-28 (passed) |
| DEF-FACT-004 | P1 | Missing automated performance regression gate (FDA-017). | Contract audit | `tests/test_scale_and_perf.py::test_fda_017_performance_regression_against_baseline` added | FIXED 2026-09-28 (passed) |

## Lifecycle

`OPEN → FIXED` (with re-test evidence) or `OPEN → MITIGATED` (workaround +
root-cause tracking ID) or `→ WONTFIX` (justification required for P0/P1).
Every defect links the failing case ID from `TEST_CASES.md`.

