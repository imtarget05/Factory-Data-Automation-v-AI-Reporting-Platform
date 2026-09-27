# Factory Data Automation + AI Reporting — Interview Evidence Kit

> Shoe-factory ETL → KPI → dashboard → AI report → Excel/PDF + alerts.
> Verified: bare-clone suite **24 passed** (was 2 failed/22 passed); seeded
> fixture `random.Random(42)` + `numpy default_rng(42)` + `Faker.seed(42)`,
> 5 CSV SHA-256 pinned. `RECRUITER-EVIDENCE.md` is the deep audit; this file is
> the interview narrative. Phase-2 addition: 5 tests + 2 skips.

---

## 1. STAR story

**Situation.** Factory reporting was manual copy-paste/filter/pivot/chart/write
across Excel files — slow, unrepeatable, and the repo's own suite failed on a
bare clone (2 failed, 22 passed) because gitignored `data/raw` could not be
regenerated.

**Task.** Automate the full pipeline (import → clean → 8 KPI groups → 10-page
dashboard → Excel/PDF + threshold alerts) and make the test suite green from a
bare clone with byte-reproducible fixtures.

**Action.**
- Seeded generator (`scripts/generate_sample_data.py`, 3× seed 42,
  `lineterminator="\n"`) + session autouse fixture regenerating CSVs only when
  absent; `make setup`/`make test` (wrapping individually-verified commands).
- Format-agnostic ingestion (`discover_files` + alias lists, CSV/Excel
  dispatch), cleaning stage (dedup, median/`Unknown_` impute, date coerce,
  qty-clip at zero), 8-group KPI engine (achievement/reject/yield, OEE
  76.02 on final day, utilisation, productivity, stock value, Pareto).
- Threshold alerts (reject>5%, stock<200, downtime>30min), one-click Excel
  (11 sheets, 337,717 B) + PDF export, timestamped Parquet + JSONL run logs.

**Result.** 24/24 green on bare clone (clean-clone proof re-ran, same 5
SHA-256); generator hash-seed independent (`PYTHONHASHSEED=12345` → identical).
Honestly documented gaps: alert/exporter/dashboard paths NOT covered by tests,
"84+ KPIs" and "95% time saved" claims marked NOT VERIFIED.

## 2. System-design Q&A

**Q1: Why a seeded generator instead of committing sample CSVs?**
CSVs are bulky, drift silently, and gitignore already excludes them. A seeded
generator makes the fixture a function of 3 integers — byte-identical across
OS/process hash seeds, verifiable by SHA-256, regenerable forever.
Cost: generator code must itself avoid clock/env/salted-hash inputs (the old
`data_generator.py` failed exactly this way and was bypassed, not patched).

**Q2: Why SQLite-default/ephemeral instead of managed Postgres on free tier?**
(See `docs/adr/0001-*`.) The pipeline is batch: ETL → Parquet/SQLite → renders.
Managed Postgres adds provisioning, credentials, and egress cost for zero
analytical benefit at this scale; SQLite + Parquet artefacts are the store and
the cache. Postgres becomes right when concurrent writers or row-level
multi-user access appear — not before.

**Q3: Why structured JSONL logs instead of plain prints?**
Every stage emits machine-greppable events (`etl_start`, `data_cleaned`,
`kpis_calculated`) with row counts — the dedup evidence (9/54/111/36/48 rows)
came from logs, not tests. Plain prints cannot be aggregated into the alerts
summary or a future Grafana/Loki tail.

**Q4: SPOF / what breaks at 10× data?**
Single-process pandas holds all frames in RAM; the 11k-row demo is trivial but
100× data OOMs the Streamlit cache loader. Scale path: Polars lazy frames
(already a dependency) + partitioned Parquet + per-dataset incremental runs —
scheduler (`APScheduler`) and FastAPI exist for exactly that evolution.

## 3. Live-demo script (5 steps)

```bash
# 1. Regenerate fixtures deterministically, verify hashes
python -m scripts.generate_sample_data && sha256sum data/raw/*.csv
# 2. Run the suite from a bare-clone state (deletes CSVs first to prove it)
rm data/raw/*.csv && python -m pytest -q            # -> 24 passed
# 3. Run the real pipeline, watch structured stage logs
python -m app.etl.pipeline                          # discovered files + data_cleaned counts
# 4. Compute KPIs (final-day OEE ≈ 76.02) and export Excel + PDF
python -c "from app.etl.kpi_engine import calculate_all_kpis; ..."  # then Export page
# 5. Launch the 10-page dashboard
streamlit run app/dashboard/run.py                  # -> http://localhost:8501
```

| Step | URL / command | Expected |
|---|---|---|
| 1 | `sha256sum data/raw/*.csv` | 5 pinned SHA-256 (see RECRUITER-EVIDENCE.md) |
| 2 | `pytest -q` | 24 passed, no manual fixture step |
| 4 | export | `.xlsx` ~337 KB + `.pdf` in `data/exports/` |
| 5 | `http://localhost:8501` | 10 pages: Overview…User Guide |
