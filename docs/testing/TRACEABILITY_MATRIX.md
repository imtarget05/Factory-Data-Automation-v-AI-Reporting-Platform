# Traceability Matrix — Factory Data Automation + AI Reporting

`Requirement → Business Rule → Test Case → Automated Test → Execution Evidence`

| Business invariant | Test Case | Automated test (exact node, on disk) | Source file | Evidence |
|---|---|---|---|---|
| QUARANTINE_NEVER_SILVER (invalid → quarantine, pipeline survives) | FDA-002–006, FDA-010, FDA-016 | `test_negative_target_qty_is_violation`, `test_future_date_is_violation_on_all_datasets`, `test_text_in_number_cell_is_violation`, `test_bad_rows_are_dropped_not_imputed`, `test_gate_runs_in_load_and_clean_all`, … | `tests/test_contracts.py`, `tests/test_quarantine.py` | VERIFIED 56 passed |
| CSV_FORMULA_NEUTRALIZED (`= + - @` inert) | FDA-011 | `test_formula_payloads_are_neutralized`, `test_sanitized_cells_round_trip_as_single_inert_field`, `test_benign_cells_untouched`, `test_real_exporter_flags_formulas_when_deps_available` | `tests/test_csv_injection.py` | VERIFIED 4 passed |
| IDEMPOTENT_INGEST (2× ingest == 1×) | FDA-008 | `test_double_run_yields_identical_aggregates`, `test_duplicated_input_rows_do_not_duplicate_aggregates`, `test_real_clean_dataframe_double_run_when_pandas_available` | `tests/test_etl_idempotency.py` | VERIFIED 3 passed |
| ENGINE_PARITY (Pandas vs Polars aggregates equivalent) | FDA-009 | `test_fda_009_pandas_polars_synthetic_parity`, `test_fda_009_pandas_polars_raw_files_parity[*]`, `test_fda_009_downstream_kpi_parity` | `tests/test_polars_parity.py` | VERIFIED 7 passed (DEF-FACT-002 FIXED) |
| KPI_EXACT (OEE = A×P×Q) | FDA-014 | `test_calculates_achievement`, `test_oee_components`, `test_utilization_rate`, `test_stock_value`, `test_defect_types`, `test_units_per_hour` | `tests/test_kpi.py` | VERIFIED 12 passed |
| SCALE_SURVIVABILITY & PERF_GATE | FDA-013, FDA-017 | `test_fda_013_scale_10x_pipeline_survives`, `test_fda_017_performance_regression_against_baseline` | `tests/test_scale_and_perf.py` | VERIFIED 2 passed (DEF-FACT-003, DEF-FACT-004 FIXED) |
| SELECT_ONLY_SQL (DELETE/DROP/multi blocked, never 500) | FDA-021–025 | `test_specs_never_mutate_the_frames`, `test_delete_is_rejected_422_not_500`, `test_drop_is_rejected_422_not_500`, `test_timeout_clamped_and_respected`, `test_malformed_bodies_never_500` | `tests/test_sql_tool.py`, `tests/test_query_api.py` | VERIFIED (25 passed + 3 skipped LAN vLLM) |
| PARQUET_DUCKDB_PARITY | FDA-018–020 | `test_silver_parquet_roundtrip`, `test_oee_sqlite_parity`, `test_oee_duckdb_parity` | `tests/test_silver_parquet.py`, `tests/test_oee_parity.py` | VERIFIED (5 passed + 1 skip duckdb opt) |

