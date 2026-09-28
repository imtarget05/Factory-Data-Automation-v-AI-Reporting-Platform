# Test Plan — Factory Data Automation + AI Reporting

**Contract:** [`docs/qa/QA_ACCEPTANCE.md`](../../docs/qa/QA_ACCEPTANCE.md) (gates, verdicts, evidence standard).
**Case IDs:** `FDA-001` → `FDA-025` in `TEST_CASES.md`.
**Runner:** `/tmp/factorygen/bin/python -m pytest` (has pytest+pandas). On disk: 10 files,
**111 `def test`** (enumerated 2026-09-27). Full single-command run exceeds 180 s
cumulatively (~7 min) — run per-file, not one shot.

## Scope

Bronze→Silver→Gold ETL (Pandas + Polars parity), Pydantic data contracts,
quarantine pipeline, Parquet/DuckDB layer, Text-to-SQL gateway (allow-list +
injection block), KPI correctness (OEE/Yield/Pareto), performance baseline.

## Levels

| Level | What | Where |
|---|---|---|
| Unit | contract validation (21), KPI math on fixed fixtures (12) | `test_contracts.py`, `test_kpi.py` |
| Integration | ETL end-to-end (14), Parquet round-trip (4), DuckDB/SQLite parity (2) | `test_etl.py`, `test_silver_parquet.py`, `test_oee_parity.py` |
| Property | quarantine gate idempotence, dedup collapse, double-run identical aggregates | `test_quarantine.py` (23), `test_etl_idempotency.py` (3) |
| Adversarial | CSV injection (4), SQL DELETE/DROP/multi-statement blocked (18+10) | `test_csv_injection.py`, `test_sql_tool.py`, `test_query_api.py` |
| Concurrency | duplicate ingestion (idempotency), Pandas/Polars parity | `test_etl_idempotency.py` |
| Performance | ×10/×100 dataset, regression vs `benchmarks/baseline_phase1.json` | UNVERIFIED here (NOT A GATE) |
| E2E | valid 5-file import → Gold KPIs, no quarantine | staging run |

## Environments

| Env | Command | Scope |
|---|---|---|
| Offline | per-file pytest (see execution report) | all 10 files runnable: **118 passed, 1 failed, 4 skipped** 2026-09-27 |
| CI | `pytest -q` | full suite incl. real exporter path (needs pandas+reportlab+dotenv) |
| Live-infra | gateway on `:8787` | FDA-015 fallback (rule playbook when gateway down) |

## Entry / exit criteria

- Entry: fixture datasets + contracts frozen for the run.
- Exit: all P0 PASS per contract §3; P1 PASS or documented exception; evidence archived.

## Invariant under test

```text
invalid record -> quarantine, never Silver/Gold
duplicate ingest == single ingest
SQL gateway: SELECT only; anything else blocked, never executed
```
