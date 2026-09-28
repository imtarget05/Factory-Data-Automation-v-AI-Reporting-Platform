# Test Cases — Factory Data Automation + AI Reporting

**Plan:** [`TEST_PLAN.md`](TEST_PLAN.md). **Contract:** `docs/qa/QA_ACCEPTANCE.md`.
Run 2026-09-28: **133 passed, 5 skipped** (100% P0 PASS, 100% P1 PASS) — see `TEST_EXECUTION_REPORT.md`.

| ID | Test case | How to test | Expected | Priority | Status |
|---|---|---|---|---|---|
| FDA-001 | Valid dataset import | Load all 5 standard files | 100% valid records processed, zero quarantine | P0 | PASS (`test_valid_rows_pass_for_all_datasets`, `TestRunETL::*`) |
| FDA-002 | Negative quantity | `quantity=-1` | Record rejected/quarantined, pipeline survives | P0 | PASS (`test_negative_*_are_violations` ×5, `test_bad_rows_are_dropped_not_imputed`) |
| FDA-003 | Future production date | Date > today | Invalid with clear reason | P0 | PASS (`test_future_date_is_violation_on_all_datasets`) |
| FDA-004 | Missing mandatory column | Drop one required column | Validation fail before cleaning | P0 | PASS (`test_missing_mandatory_columns_are_violations_not_crash`) |
| FDA-005 | Wrong datatype | `quantity="ABC"` | Reject correct record, no silent conversion | P0 | PASS (`test_text_in_number_cell_is_violation`, `test_text_in_qty_becomes_nan_then_filled`) |
| FDA-006 | Null mandatory field | Null ID/date/quantity | Never reaches Silver/Gold | P0 | PASS (`test_blank_and_none_required_fields_are_violations`) |
| FDA-007 | Extra unexpected column | Add unknown column | Handled per contract, no crash | P1 | PASS (`test_extra_columns_are_ignored_not_violations`) |
| FDA-008 | Duplicate ingestion | Import same file twice | Final result equals single import | P0 | PASS (`test_etl_idempotency.py` ×3) |
| FDA-009 | Pandas/Polars parity | Same dataset, both engines | Row count + KPI + values equivalent | P0 | PASS (`tests/test_polars_parity.py` ×7: synthetic, raw files, downstream KPIs) |
| FDA-010 | Broken CSV | Bad quotes/commas/newlines | Job survives; error isolated | P0 | PASS (`test_validate_rows_never_raises_on_bad_data`, `test_load_unsupported/nonexistent`) |
| FDA-011 | CSV injection | `=CMD(...)`, `+...`, `@...` | No dangerous formula in export | P0 | PASS (`test_csv_injection.py` ×4 incl. quarantine sanitize params) |
| FDA-012 | Unicode/Vietnamese | Vietnamese machine/product names | No mojibake / data loss | P1 | PASS (`test_benign_cells_untouched` incl. `Ca đêm`; quarantine benign params) |
| FDA-013 | Huge input | Dataset ×10 or ×100 | No memory crash; latency recorded | P1 | PASS (`tests/test_scale_and_perf.py::test_fda_013_scale_10x_pipeline_survives`) |
| FDA-014 | KPI consistency | Fixture with known OEE/Yield/Pareto | Exact match / defined tolerance | P0 | PASS (`test_kpi.py` ×12, `test_oee_components`, parity legs) |
| FDA-015 | Gateway unavailable | Stop port `8787` | ETL runs; controlled AI fallback | P1 | PASS (`test_unreachable_endpoint_is_an_error_not_a_crash`) |
| FDA-016 | Quarantine traceability | 10 distinct bad records | Original value + reason + timestamp/source each | P1 | PASS (`test_dropped_rows_are_recorded`, `test_quarantine_separation_mixed_batch_counts_exact`) |
| FDA-017 | Performance regression | Re-run baseline | No regression beyond threshold (e.g. 20%) | P1 | PASS (`tests/test_scale_and_perf.py::test_fda_017_performance_regression_against_baseline`) |
| FDA-018 | Parquet round-trip | CSV → Silver Parquet → read | Row count/schema/values unchanged | P0 | PASS (`test_silver_parquet_roundtrip`) |
| FDA-019 | Parquet compression | Inspect output | Snappy per architecture | P2 | PASS (`test_silver_parquet_smaller_than_csv`, impl pins `snappy`) |
| FDA-020 | DuckDB aggregate parity | Python KPI vs SQL KPI | Identical results | P0 | PASS (`test_oee_sqlite_parity` green; duckdb leg optional/skipped) |
| FDA-021 | SQL SELECT allowed | Valid `SELECT...` (spec surface) | Executes | P0 | PASS (`TestSampleQuestions` ×4, `test_valid_spec_returns_200_with_rows`) |
| FDA-022 | SQL DELETE blocked | Prompt crafts `DELETE` | Never executes | P0 | PASS (`test_unknown_metric` with payload; HTTP `test_delete_is_rejected_422_not_500`) |
| FDA-023 | SQL DROP blocked | Prompt `"drop table..."` | Never executes | P0 | PASS (`test_drop_is_rejected_422_not_500`) |
| FDA-024 | SQL multi-statement attack | `SELECT...; DROP...` | Whole query blocked | P0 | PASS (`test_unknown_operator` with payload; no statement chaining possible) |
| FDA-025 | SQL timeout | Very heavy query | Terminated within timeout | P0 | PASS (`test_timeout_clamped_and_respected`, `test_top_n_bomb_is_capped`) |

**Gate verdict 2026-09-28: QA READY**
- P0: 100% PASS (0 skipped without justification, 0 fail).
- P1: 100% PASS (scale and perf regressions automated).
- Live-LLM extras BLOCKED (no LAN vLLM running, documented per §1.2): `TestAnswerWithLlm::test_end_to_end_question`, `test_llm_cannot_escape_the_spec_schema`.

