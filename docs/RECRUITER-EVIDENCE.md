# Recruiter Evidence

Every row below was verified by hand on Windows / Python 3.11.0 / pandas 3.0.6 / pytest, in this
repository, by reading the file, running the named test, and running the named command. Rows with
no test coverage are marked **NOT VERIFIED** and are **not** claimed as tested.

Repair context: before this work `pytest` reported `2 failed, 22 passed`. The two failures were
`TestDiscoverFiles::test_discover_finds_csv` and `TestDiscoverFiles::test_discover_has_expected_keys`,
because `.gitignore` excludes the contents of `data/raw/`, `data/processed/` and `data/exports/`
and nothing in the repository could regenerate them.

---

## Shipped a byte-reproducible test fixture for gitignored data, turning a 2-failure suite green on a bare clone

- **IMPLEMENTATION**: `scripts/generate_sample_data.py:278` builds all five datasets from three
  explicitly seeded sources — `random.Random(42)` (`:280`), `numpy.random.default_rng(42)` (`:281`)
  and `Faker.seed(42)` (`:282`). It reads no clock, no environment and no salted `hash()`, so the
  output does not change between runs, machines or interpreter invocations.
  `write_datasets()` (`:293`) pins `lineterminator="\n"` (`:300`) so the bytes are identical on
  Windows and Linux. `tests/conftest.py:27` adds a session-scoped autouse fixture that runs the
  generator only when `data/raw/` contains no CSV (`:30`, `:34`), so `pytest` alone is sufficient on
  a fresh clone. `Makefile` exposes `make setup` and `make test`.
- **FILE**: `scripts/generate_sample_data.py`, `scripts/__init__.py`, `tests/conftest.py`, `Makefile`
- **TEST**: `tests/test_etl.py:19` `test_discover_finds_csv` asserts at least one discovered path
  ends in `.csv`; `tests/test_etl.py:24` `test_discover_has_expected_keys` asserts
  `{"production","quality","inventory","machine","workers"}` is a subset of the keys returned by the
  real `discover_files()`. Both previously failed on a bare clone and now pass against real files.
- **RUNTIME EVIDENCE**:
  - Before: `2 failed, 22 passed, 1 warning in 1.16s`
  - After: `24 passed, 16 warnings in 1.74s`
  - Reproducibility, generator run twice, SHA-256 identical on both runs:
    `production.csv C0214DD3E740649DCE87E9A6AB59BEDBE51E45ED72537640BB180AE6E9391C43`,
    `quality.csv 615CDE36453D1A7451F9EF06B2F130C4C7C20846C55AF6E572BBA8A8704CD1CB`,
    `inventory.csv 0AEF4DFC2D6ACC47996487D619455C1CD319A866527C640C90E4D4490424B1EB`,
    `machine.csv F803BF074BA84E1B78EC85538C606484BE9075EF392E47A5283A843FA83B49B4`,
    `workers.csv 5BB9955542188DD087D1CA400A53C286D97EE130C4F4C2509826180DEA3F9654`
  - Clean-clone proof: all five CSVs deleted (`data/raw` left with only `.gitkeep`), then
    `python -m pytest -q` run with no other step -> `24 passed, 16 warnings in 3.17s`. The files the
    fixture generated hashed to the same five SHA-256 values above.
  - Hash-seed independence: re-ran the generator with `PYTHONHASHSEED=12345` -> same five hashes.
    (The pre-existing `app/utils/data_generator.py:98-99` uses `hash(product)`, which is salted per
    process, and `datetime.now()` at `:56, :81, :124, :176, :210`; that is why it cannot be seeded
    and why a new generator was written rather than wiring the old one to the tests.)
  - Lint: `python -m ruff check scripts/generate_sample_data.py scripts/__init__.py tests/conftest.py`
    -> `All checks passed!` (exit 0). Repo-wide `python -m ruff check .` reports `Found 630 errors`,
    all of them pre-existing in `app/`, `notebooks/`, `scripts/measure_time_saved.py`,
    `tests/test_etl.py`, `tests/test_kpi.py`; I did not add to that count and did not touch those files.
  - `make setup` / `make test` are **NOT VERIFIED**: GNU `make` is not installed on this Windows
    machine, so the Makefile was written but never executed. The commands it wraps
    (`pip install -r requirements.txt`, `python -m scripts.generate_sample_data`,
    `python -m pytest tests/ -v`) were each run individually.

---

## Built a format-agnostic ingestion layer that auto-classifies raw files into named datasets

- **IMPLEMENTATION**: `app/etl/pipeline.py:17` `discover_files()` globs `*.csv`, `*.xlsx`, `*.xls`
  from `data/raw` and maps each file to one of five dataset keys using a primary name plus alias
  list (`:25-31`) — e.g. `machine` matches `machine|mach|equipment`, `workers` matches
  `workers|worker|employee|staff`. `load_file()` (`:55`) dispatches on extension to `read_csv` or
  `read_excel(engine=openpyxl|xlrd)`. `load_and_clean_all()` (`:127`) discovers, loads, cleans and
  returns all five frames; `run_etl()` (`:171`) also persists them. Failure logging is structured,
  not silent.
- **FILE**: `app/etl/pipeline.py:17-52` (discovery), `:55-71` (loading), `:127-151` (orchestration)
- **TEST**: `tests/test_etl.py:24` `test_discover_has_expected_keys` asserts all five keys are
  discovered; `tests/test_etl.py:15` `test_discover_returns_dict` asserts the return type;
  `tests/test_etl.py:32` `test_load_csv` loads `data/raw/production.csv` and asserts a non-empty
  frame; `tests/test_etl.py:39` `test_load_nonexistent` and `:43` `test_load_unsupported` assert
  `None` for a missing path and an unsupported extension.
- **RUNTIME EVIDENCE**: `python -m app.etl.pipeline` printed
  `Discovered files: {'production': 'production.csv', 'quality': 'quality.csv', 'inventory': 'inventory.csv', 'machine': 'machine.csv', 'workers': 'workers.csv'}`
  and returned frames of shape inventory `(900, 10)`, machine `(5400, 10)`, production
  `(11160, 12)`, quality `(3600, 9)`, workers `(4801, 10)`. Suite: `24 passed, 16 warnings in 1.74s`.

---

## Implemented a data-quality stage that deduplicates, imputes, coerces, normalises and range-checks raw records

- **IMPLEMENTATION**: `app/etl/pipeline.py:74` `clean_dataframe()` drops duplicate rows (`:86`),
  fills numeric nulls with the column median and object nulls with `Unknown_<column>` (`:91-99`),
  coerces any column whose name contains `date` to datetime with `errors="coerce"` (`:102-107`),
  strips whitespace from all text columns (`:110-114`), and clips eight quantity columns at zero —
  `Target_Qty, Actual_Qty, Good_Qty, Reject_Qty, Stock_Qty, Defect_Count, Inspected_Qty,
  Units_Produced` (`:117-120`). Every call emits a structured `data_cleaned` log event with the row
  count (`:122-123`).
- **FILE**: `app/etl/pipeline.py:74-124`
- **TEST**: `tests/test_etl.py:49` `test_clean_production` asserts a negative `Target_Qty` is
  clipped to `>= 0`, a null `Actual_Qty` is filled (`notna().all()`), and no rows are lost;
  `tests/test_etl.py:63` `test_clean_removes_duplicates` exercises the dedup path;
  `tests/test_etl.py:73` `test_clean_handles_empty` asserts an empty frame is handled without error.
- **RUNTIME EVIDENCE**: on the generated data the real pipeline printed and logged
  `Removed 9 duplicates from inventory`, `Removed 54 duplicates from machine`,
  `Removed 111 duplicates from production`, `Removed 36 duplicates from quality`,
  `Removed 48 duplicates from workers` (11271 -> 11160, 5454 -> 5400, 3636 -> 3600, 4849 -> 4801,
  909 -> 900 rows), with each `data_cleaned` event reporting the post-clean row count.
  Suite: `24 passed, 16 warnings in 1.74s`.
  Known gap, stated rather than hidden: `test_clean_removes_duplicates` (`tests/test_etl.py:63`)
  only asserts `cleaned is not None`; it does **not** assert that a duplicate was removed. The
  deduplication behaviour itself is therefore evidenced by the runtime log line above, not by that
  test. I did not modify the test to strengthen it, and I did not modify the ETL logic.

---

## Computed manufacturing KPIs (achievement, reject, yield, OEE, utilisation, productivity, stock value, defect Pareto) from cleaned data

- **IMPLEMENTATION**: `app/etl/kpi_engine.py` — daily/weekly/monthly rollups with
  `Achievement_Rate_pct`, `Reject_Rate_pct`, `Yield_pct` (`:15-82`); OEE as
  Availability x Performance x Quality merged across the production and machine frames (`:85-137`);
  per-machine utilisation from status counts (`:140-162`); worker `Units_per_Hour` and
  `Defect_Rate_pct` (`:165-187`); inventory `Stock_Value` and `Products_Below_Reorder` (`:190-214`);
  defect analysis by type / severity / day (`:217-254`); `calculate_all_kpis()` fans out to all eight
  KPI groups (`:257-293`).
- **FILE**: `app/etl/kpi_engine.py`
- **TEST**: `tests/test_kpi.py:21` `test_calculates_achievement` asserts the three production rate
  columns exist on a real groupby; `tests/test_kpi.py:43` `test_oee_components` asserts
  `OEE_pct/Availability_pct/Performance_pct/Quality_pct` are produced by a cross-dataset merge;
  `tests/test_kpi.py:76` `test_utilization_rate` asserts an exact value
  (`Utilization_pct == 66.67` for 2 Running readings out of 3); `tests/test_kpi.py:100`
  `test_stock_value` asserts `Stock_Value` and `Total_Stock`; `tests/test_kpi.py:123`
  `test_defect_types` asserts the `by_type`/`by_severity`/`daily` result keys;
  `tests/test_kpi.py:146` `test_units_per_hour` asserts an exact `80/8 == 10.0`. Each KPI function
  also has a `test_empty_input` case asserting a DataFrame is returned for `None` input
  (`:16, :38, :71, :95, :119, :141`).
- **RUNTIME EVIDENCE**: `calculate_all_kpis` on the generated 90-day dataset logged
  `kpis_calculated: ["daily_production","weekly_production","monthly_production","oee",
  "machine_utilization","worker_productivity","inventory_kpi","defect_analysis"]`, and the final
  day computed `Availability_pct 84.0, Performance_pct 94.82, Quality_pct 95.44, OEE_pct 76.02`.
  Suite: `24 passed, 16 warnings in 1.74s`.

---

## Implemented threshold alerting across quality, inventory, machine and OEE signals

- **IMPLEMENTATION**: `app/reports/alert_system.py` — `Alert` value object with `to_dict()` (`:18-30`),
  and `AlertManager` running four rule sets: production/reject rate (`:46`), inventory below reorder
  point (`:78`), machine failure / temperature / vibration (`:115`) and low OEE (`:179`), aggregated
  by `check_all()` (`:199`) with a severity summary from `get_summary()` (`:223`). Thresholds live in
  `app/utils/config.py:35-37` (`ALERT_REJECT_RATE = 5.0`, `ALERT_INVENTORY_MIN = 200`,
  `ALERT_DOWNTIME_MIN = 30`).
- **FILE**: `app/reports/alert_system.py`, `app/utils/config.py:34-37`
- **TEST**: `tests/test_alert_trigger.py` now exists (2 tests, both passing) — reject-rate
  trigger at runtime, severity ordering and `to_dict()` serialization. The original manual
  observation below remains as recorded; the marker is downgraded from *no coverage* to
  *covered by tests and previously by a manual run*.
- **RUNTIME EVIDENCE**: `AlertManager().check_all(datasets, kpis)` returned 16 alerts and logged
  `alert_check_complete {"total": 16, "critical": 6, "warnings": 10}`; `get_summary()["by_level"]`
  was `{'CRITICAL': 6, 'WARNING': 10, 'INFO': 0}`.

---

## Generated one-click Excel and PDF management reports from the computed KPIs and alerts

- **IMPLEMENTATION**: `app/reports/exporter.py` — `export_to_excel()` (`:26`) writes up to eleven
  named sheets via `pd.ExcelWriter(engine="openpyxl")` (daily/weekly/monthly production, OEE, machine
  utilisation, worker productivity, inventory, defects by type/severity/day, alerts);
  `export_to_pdf()` (`:76`) builds a styled A4 report with reportlab — branded title, executive
  summary, key-metric table, 7-day production table, active-alert table, problems and
  recommendations (`:101-210`); `export_all()` (`:214`) does both and returns the paths.
- **FILE**: `app/reports/exporter.py`
- **TEST**: **NOT VERIFIED** — no test in `tests/` exercises `app/reports/exporter.py`. I did not add
  one; the runtime observation below is a manual end-to-end run, not a suite result.
- **RUNTIME EVIDENCE**: calling `ReportExporter().export_all(kpis, alerts)` on the generated data
  printed `Excel report saved: .../data/exports/factory_report_20260926_033920.xlsx` and
  `PDF report saved: .../data/exports/factory_report_20260926_033927.pdf`; the files exist at
  337,717 bytes (Excel) and 3,497 bytes (PDF). One pre-existing warning is emitted by the repo's own
  code: `app/reports/exporter.py:141: UserWarning: obj.round has no effect with datetime, timedelta,
  or period dtypes` (pandas 3 behaviour on the `Date` column). Reported, not suppressed.

---

## Persisted cleaned datasets as timestamped Parquet and emitted structured JSON run logs

- **IMPLEMENTATION**: `app/etl/pipeline.py:154` `save_processed()` writes one
  `<dataset>_<YYYYmmdd_HHMMSS>.parquet` per frame with `index=False`; `run_etl()` (`:171`) calls it
  whenever datasets were loaded. `app/utils/logging_config.py` `log_event()` serialises each stage
  (`etl_start`, `loading_dataset`, `data_cleaned`, `etl_complete`, `saved_processed`) as single-line
  JSON with `timestamp`, `level`, `logger`, `component` and a `context` object.
- **FILE**: `app/etl/pipeline.py:154-176`, `app/utils/logging_config.py`
- **TEST**: indirectly only — `tests/test_etl.py:81` `test_run_etl_returns_dict` and `:85`
  `test_run_etl_has_data` call the real `run_etl()`, which executes the Parquet write and the log
  emission as a side effect, but neither asserts on the artefacts. **NOT VERIFIED** as a direct test
  of the Parquet or logging output.
- **RUNTIME EVIDENCE**: `run_etl()` logged `saved_processed` for all five datasets
  (`inventory_20260926_033917.parquet`, `machine_...`, `production_...`, `quality_...`,
  `workers_...`) followed by `all_processed_saved {"directory": "...\\data\\processed"}`. Suite:
  `24 passed, 16 warnings in 1.74s`.

---

## Shipped a 10-page Streamlit/Plotly dashboard over the same ETL and KPI layer

- **IMPLEMENTATION**: `app/dashboard/run.py` — a cached loader (`:52-64`) that runs `run_etl()`,
  `calculate_all_kpis()` and `AlertManager.check_all()`, then ten page renderers
  (`:67, :242, :322, :388, :463, :580, :687, :720, :787, :818`) wired to a sidebar radio at
  `:893-899` (Overview, Production, Quality, Inventory, Machine, AI Report, AI Chat, Export, Data,
  User Guide). It calls the same `ReportExporter` (`:736, :756, :774`).
- **FILE**: `app/dashboard/run.py`
- **TEST**: **NOT VERIFIED** — there is no dashboard test, and I did not launch Streamlit to confirm
  it renders. This row is listed because the capability is a real CV bullet, but it is not claimed
  as verified and no run output is offered as evidence.

---

## Put a fail-closed data-quality gate in front of the LLM, so no narrative can be generated from untrusted numbers

- **IMPLEMENTATION**: `app/data_contracts/quality_gate.py` — `QualityDecision` (`:43`) with the three
  statuses `GOOD`/`BAD`/`UNKNOWN` (`:29-31`), a NaN/±inf `_finite_check()` (`:68`) that also catches
  checks that raise, dataset/KPI completeness checks, and a quarantine-rate check against
  `QUARANTINE_RATE_MAX = 0.5` (`:39`). `evaluate_quality(datasets, kpis, quarantine)` (`:104`)
  returns a decision and never raises: any internal error degrades to `UNKNOWN`, which blocks.
  `app/ai/reporting.py` consumes it at the single authorization boundary
  `generate_report()` (`:211`) → `_blocked_report()` (`:297`) for `BAD`/`UNKNOWN`, with
  `generation_mode="NOT_RUN"`, `evidence=None`, `provenance=[]`, and **no LLM call**.
  `extract_kpi_evidence()` (`:77`) builds the machine-readable evidence snapshot
  (`snapshot_id = "snap-" + sha256(canonical kpis+sources)`); `validate_provenance()` (`:124`)
  drops any cited id that is not in `evidence["source_ids"]`; `_finalize_report()` (`:321`)
  attaches gate/evidence **after** the narrative so the model cannot overwrite them.
  `_json_safe()` (`:29`) coerces numpy scalars/NaN/DataFrames so the payload is strictly
  JSON-representable. `app/api/main.py` `_quality_context()` (`:286`) feeds the row-level
  quarantine DLQ into the gate, wired into `/api/v1/report` and `/api/v1/export`.
- **FILE**: `app/data_contracts/quality_gate.py`, `app/ai/reporting.py`, `app/api/main.py`
- **TEST**: `tests/test_ai_quality_gate.py` — 19 tests covering `GOOD` (`:106`), NaN (`:113`),
  ±inf (`:121`), missing dataset (`:128`), empty dataset (`:136`), missing KPI input (`:143`),
  quarantine-rate breach (`:149`) and normal rate (`:156`), gate-error → `UNKNOWN` (`:162`),
  LLM called once on `GOOD` (`:171`), honest `FALLBACK` labelling (`:183`), four
  block-with-zero-LLM-calls cases (`:193`, `:206`, `:216`, `:226`), model attempting to
  override gate/status (`:235`), fabricated provenance rejected (`:249`), snapshot
  determinism (`:259`) and provenance set membership (`:273`).
  `tests/test_reporting_boundary.py` — 9 tests driving the real HTTP surface: JSON-native
  payload (regression for a 500, see below), `_json_safe` coercion of numpy/NaN/frames, no
  false provenance count on fallback, deterministic reports modulo the audit
  stamp, DLQ →
  gate, blocked-is-200-not-500, blocked-over-HTTP-makes-zero-LLM-calls,
  good-over-HTTP-makes-one-LLM-call, and gate/block logging events.
- **RUNTIME EVIDENCE**:
  - `python -m pytest -q` → `288 passed, 5 skipped, 4 xfailed in 14.29s`.
  - Mutation controls `tests/test_ai_quality_mutations.py` `M1`–`M4` monkeypatch each check
    into a no-op (finite check, dataset presence, quarantine rate, provenance membership) and
    assert the gate then lets bad data through. All four are `xfail` **by design** and reported
    as `4 xfailed`: they must never pass. If one passes, the mutation was not neutralized.
  - Determinism over the real 26 119-row dataset, two consecutive runs:
    `snapshot=snap-38c77a0e903797c5` both times, and the canonical JSON of
    `{evidence, quality, provenance, generation_mode, status}` hashes to
    `68649edbce3c30f3a06c900d12a182d2` both times. The single excluded field is
    `quality.evaluated_at_epoch` (wall clock, renamed from `timestamp` precisely
    so it cannot be mistaken for deterministic content). Stated precisely: the
    business evidence and the quality-decision content are a pure function of the
    input data, with evaluation time isolated as metadata. This is **not** a
    claim that the entire HTTP response is byte-identical.
  - Live generation: `/api/v1/report` on the real data returned `quality=GOOD`,
    `mode=FALLBACK` (Ollama was not running — correctly labelled, not passed off as model
    output), `snapshot=snap-38c77a0e903797c5`.
- **A real bug this found, rather than a claim it prevented**: `GET /api/v1/report` returned
  **500** on the local build. `ValueError: [TypeError("'numpy.int64' object is not iterable"),
  TypeError('vars() argument must have __dict__ attribute')]` from FastAPI's `jsonable_encoder` —
  a `numpy.int64` inside the nested KPI dict reached the response body (numpy ints are *not*
  Python ints, so the encoder cannot serialise them). The 19 gate tests did not catch it because
  their fixtures use plain Python ints. Fixed by `_json_safe()` at evidence construction, and
  pinned by `test_report_endpoint_returns_json_native_payload`, which walks every leaf and
  asserts it is a JSON-native type.

---

## Wired the existing AlertManager to runtime conditions and gave it test coverage

- **IMPLEMENTATION**: no new alerting framework. `app/reports/alert_system.py` `AlertManager`
  was reused as-is; the gate work added tests for it because a blocked report and an active
  alert are the same operator signal.
- **FILE**: `app/reports/alert_system.py` (unchanged), `tests/test_alert_trigger.py` (new)
- **TEST**: `tests/test_alert_trigger.py:50` `test_alert_condition_triggers_at_runtime` asserts a
  reject rate over 5% raises a CRITICAL alert and one under it does not; `:70`
  `test_alert_summary_counts_and_orders_by_severity` asserts `get_summary()` counts by level
  and orders CRITICAL before WARNING, plus `to_dict()` serialization.
  This supersedes the **NOT VERIFIED** marker previously recorded for `alert_system.py` — it
  is now covered by the suite, not only by a manual run.
- **RUNTIME EVIDENCE**: `python -m pytest tests/test_alert_trigger.py -q` → `2 passed`.

---

## Claims in the README that I could NOT verify, and therefore do not stand behind

- **"84+ KPIs"** — `calculate_all_kpis` returns eight KPI *groups* (`app/etl/kpi_engine.py:257-293`).
  I did not count individual metrics to 84, so this number is unverified.
- **"AI Reporting: local Qwen2.5 generates Summary, Problems, Recommendations, Risks"** — the code
  exists (`app/ai/reporting.py`, `app/ai/local_llm.py`, wired at `app/dashboard/run.py:580`) and a
  fallback path is present. **Still NOT VERIFIED that Ollama/Qwen produced output**: no Ollama
  endpoint was reachable during this audit (`Cannot connect to Ollama: [Errno 61] Connection
  refused`), so every observed report run took the deterministic `FALLBACK` path and is labelled
  `generation_mode: "FALLBACK"` rather than `REAL_MODEL`. What *is* verified: the gate, the
  fallback labelling, evidence snapshots, provenance validation and zero-LLM-call blocking
  (19 + 9 tests, section above), using an injected fake LLM.
- **`scripts/measure_time_saved.py` time-savings figures** — the script computes a hard-coded
  `750` second manual baseline (`scripts/measure_time_saved.py:33`) and a hard-coded `12` second
  "AI" time (`:48`), then sleeps 0.1 s per step. It estimates; it does not measure a real manual
  process. Treat any "95% time saved" claim as **NOT VERIFIED** and unsupported by measurement.
- **CI status** — `.github/workflows/ci.yml` exists and defines lint/test/security/docker jobs, but
  I did not run `gh run list`, so whether the workflow passes is **NOT VERIFIED**. Note also that the
  workflow's lint step runs `ruff check app/ tests/` while the repo currently has 630 pre-existing
  ruff findings in those paths, so that job would be expected to fail as written. I did not change
  the workflow.
- **Docker** — `docker/Dockerfile` and `docker/docker-compose.yml` exist; I did not build the image.
  **NOT VERIFIED.**
- **The live Azure deployment does not yet run the quality gate.** Revision
  `ca-factory-api--0000001` (traffic weight 100, created 2026-09-30T13:27:17Z) runs image tag
  `...factory-api:4e4e8b58d0551a080ea6750deb3f2a1ce9c98265`, digest
  `sha256:675fd4f2782308fb2779d29130cdd17006bc449958613d6fc023d3c31c5728f2` (digest confirmed
  independently with `docker buildx imagetools inspect`). That commit is `4e4e8b58`, which predates
  `app/data_contracts/quality_gate.py` (still untracked in git). Probing the live
  `/api/v1/report` confirms it: the response has keys
  `date, key_metrics, problems, recommendations, risks, root_causes, summary, title` and **no**
  `generation_mode`, `quality`, `evidence` or `provenance`. The gate is verified locally and on
  the test HTTP surface, **not** in the running cloud revision. Live `/api/v1/health`, `/data`,
  `/kpis`, `/report` and `/metrics` all returned 200 when probed on 2026-09-30, and `/metrics-evil`
  returned 404 (prefix-boundary matching works).
- **API-key enforcement in the cloud revision is open mode.** The Container App template has no
  environment variables (`environmentVariables: null`) and `FACTORY_API_KEY` is not provisioned, so
  `ApiKeyMiddleware` passes all traffic through by design (`app/api/security.py:35-36`). The
  enforced path (401 on anonymous/wrong key, open safe paths) is covered by
  `tests/test_api_key_auth.py`; production enforcement still needs the secret. **NOT VERIFIED in
  production.**
- **Probe timing caveat, stated so the evidence is not overread**: the first probe attempts hit
  Container Apps scale-from-zero and timed out at 15 s and again at 60 s; a later probe with a 90 s
  budget answered in 0.2–0.5 s. Endpoint health was therefore established only on the warm run. A
  cold-start SLA claim is **NOT VERIFIED** — and the revision template has no probes configured
  (`probes: []`), so nothing in Azure itself is watching.
