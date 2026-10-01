# 📊 Business Impact — AI-Powered Factory Data Automation

> ## ⚠️ Status of the figures below: NOT MEASURED
>
> **Every percentage and hour figure in the two tables at the top of this file is
> an UNMEASURED ESTIMATE — a planning assumption, not an observed result.**
> There is no time-motion study, no production telemetry, and no before/after
> measurement behind any of them. The only driver is
> `scripts/measure_time_saved.py`, which **simulates** the comparison; the
> simulation's own provenance is disowned in `docs/RECRUITER-EVIDENCE.md:308-311`.
>
> Treat these tables as *what the design targets*, and the lower
> "Impact / How measured" table as the part with real provenance. A single figure
> in this file is MEASURED: the ETL/KPI benchmark rows at the bottom, which name
> their script, machine and date. Nothing here is a business result.

## Time & Cost Savings Analysis

> **Status: UNMEASURED ESTIMATE — not production time-motion, not observed.**
> See the banner above.

| Task | Manual (before) | AI-Powered (after) | Savings (estimated) |
|------|----------------|-------------------|---------|
| **Daily Production Report** | 2 hours | 5 minutes | **96%** |
| **KPI Calculation (OEE, Yield, etc.)** | 30 minutes | 2 seconds | **99.9%** |
| **Report Writing (Executive Summary)** | 1 hour | 3 minutes | **95%** |
| **Data Cleaning & Validation** | 45 minutes | 5 seconds | **99.8%** |
| **Alert Monitoring (shift)** | 4 hours | Real-time | **100%** |
| **Export to PDF/Excel** | 20 minutes | 1 click (3s) | **99.75%** |
| **Quality Defect Analysis** | 1 hour | 10 seconds | **99.7%** |
| **Inventory Reorder Check** | 30 minutes | Automatic | **100%** |

## Total Daily Impact

> **Status: UNMEASURED ESTIMATE — arithmetic on the table above, not observed.**

| Metric | Value |
|--------|-------|
| **Manual hours saved per day** | ~8.5 hours |
| **Manual hours saved per month** | ~180 hours |
| **Productivity improvement** | **92%** |
| **Error reduction** | ~95% (eliminates copy-paste errors) |

## How We Calculated

- **Manual report**: HR/admin copies data from Excel → pastes into Word/PPT → formats → sends email
- **AI report**: Streamlit dashboard auto-refreshes → AI generates executive summary → 1-click export
- **Alert monitoring**: Before = human checking dashboards hourly; After = APScheduler + rule engine 24/7

## Cost Estimation (Vietnamese Market)

| Item | Manual | AI-Powered |
|------|--------|-----------|
| Daily labor cost (reporting) | ~300,000 VND (30 min) | ~5,000 VND (compute) |
| Monthly labor cost | ~6,000,000 VND | ~100,000 VND |
| Error cost (avg/month) | ~2,000,000 VND | ~100,000 VND |
| **Total monthly** | **~8,000,000 VND** | **~200,000 VND** |

> **Status: UNMEASURED ESTIMATE — market rates applied to assumed hours, not a
> measured spend.**

> 💡 **Bottom line (UNMEASURED ESTIMATE, not a result)**: if the estimates above
> hold, the design would cut factory data-reporting operational cost by roughly
> 97.5%. No production spend was measured on either side, so this is a modelled
> projection, not an observed saving.

---

## Extension (2026-09-27) — standard structure

> Existing tables above are retained for transparency but are **UNMEASURED**: their
> time/cost figures are **ESTIMATES** (plan assumptions + `scripts/measure_time_saved.py`
> simulation: 750 s manual vs 12 s AI per report) — not production time-motion
> measurements. Figures below distinguish MEASURED micro-bench from ESTIMATE.

### Problem (cost of status quo)

Raw Excel/CSV → copy-paste → pivot → charts → Word/PPT reports consumes ~8.5 h/day
(ESTIMATE, table above); OEE reconciliation across lines/shifts costs ~120 h/month
(ESTIMATE — plan assumption, pending time-motion study). Copy-paste errors propagate
into executive decisions; alerts depend on humans watching dashboards hourly.

### Solution (what the system does)

Automated pipeline: file ingest (`data/raw/`) → cleaning/validation → KPI engine
(84+ KPIs: OEE, reject, yield, utilization) → 9-page Streamlit dashboard + executive
report narratives + threshold alerts (reject>5%, inventory<200, downtime>30 min) →
one-click Excel/PDF export.

On report narratives: local Qwen2.5 when it is reachable, otherwise deterministic
fallback. **On the deployed Azure container the live endpoint returns `FALLBACK`**
because no LLM endpoint is reachable from that container — `REAL_MODEL` mode is
NOT VERIFIED on Azure (`README.md` Known gaps; `docs/RECRUITER-EVIDENCE.md:300-305`).
What gates the live report is the deterministic authorization gate, not a model.

### Impact

| Metric | Before | After | How measured |
|---|---|---|---|
| OEE reconciliation labor | 120 h/month | automated | ESTIMATE — plan assumption; pending time-motion study. Not measured here. |
| Daily reporting labor | ~8.5 h/day | minutes | ESTIMATE — from table above + `measure_time_saved.py` simulation (750 s → 12 s/report). |
| Synthetic CSV ETL aggregation, 5000 rows/iter (20 iters, local) | — | mean 296.06 ms, p95 746.05 ms | MEASURED by `scripts/bench_factory.py` (stdlib `csv` only, in-memory payload), this machine 2026-09-27. Machine-dependent; p95 reflects cold-start outlier. |
| ETL/KPI correctness | — | covered by the suite (see suite figure below) | MEASURED by the CI gate `pytest tests/ -v`. Correctness, not business latency. |

### Guardrails / SLO links

- Alert thresholds + APScheduler 24/7; structured JSON logs with request IDs;
  AI fallback template when Ollama is down.
- SLOs: `observability/slo.yaml` (job `factory` :8002, uncertain port).
- CI: `.github/workflows/ci.yml` (ruff + pytest + safety/bandid + docker).

### Reproduce

```bash
cd Factory-Data-Automation-v-AI-Reporting-Platform
python3 scripts/bench_factory.py
python3 scripts/measure_time_saved.py   # simulation behind the ESTIMATE rows
python -m pytest tests/ -v              # suite size depends on the SHA — see below
```

### Suite figure — always cite with its SHA

| Commit | Tests | Where |
|---|---|---|
| `be4ace3` (the deployed revision) | 290 | deployed build |
| `70509fc` (CI) | 288 | CI run |

Never quote a bare test count for this repo without the SHA it was measured at.
The earlier `24 passed` in this file was stale — it predated both of the above.