# 📊 Business Impact — AI-Powered Factory Data Automation

## Time & Cost Savings Analysis

| Task | Manual (before) | AI-Powered (after) | Savings |
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

> 💡 **Bottom line**: AI saves **~97.5%** of operational cost for factory data reporting.

---

## Extension (2026-09-27) — standard structure

> Existing tables above are kept as-is. Honesty note: the time/cost figures
> above are **ESTIMATES** (plan assumptions + `scripts/measure_time_saved.py`
> simulation: 750 s manual vs 12 s AI per report) — not production time-motion
> measurements. Figures below distinguish MEASURED micro-bench from ESTIMATE.

### Problem (cost of status quo)

Raw Excel/CSV → copy-paste → pivot → charts → Word/PPT reports consumes ~8.5 h/day
(ESTIMATE, table above); OEE reconciliation across lines/shifts costs ~120 h/month
(ESTIMATE — plan assumption, pending time-motion study). Copy-paste errors propagate
into executive decisions; alerts depend on humans watching dashboards hourly.

### Solution (what the system does)

Automated pipeline: file ingest (`data/raw/`) → cleaning/validation → KPI engine
(84+ KPIs: OEE, reject, yield, utilization) → 9-page Streamlit dashboard + local
Qwen2.5 executive reports + threshold alerts (reject>5%, inventory<200,
downtime>30 min) → one-click Excel/PDF export.

### Impact

| Metric | Before | After | How measured |
|---|---|---|---|
| OEE reconciliation labor | 120 h/month | automated | ESTIMATE — plan assumption; pending time-motion study. Not measured here. |
| Daily reporting labor | ~8.5 h/day | minutes | ESTIMATE — from table above + `measure_time_saved.py` simulation (750 s → 12 s/report). |
| Synthetic CSV ETL aggregation, 5000 rows/iter (20 iters, local) | — | mean 296.06 ms, p95 746.05 ms | MEASURED by `scripts/bench_factory.py` (stdlib `csv` only, in-memory payload), this machine 2026-09-27. Machine-dependent; p95 reflects cold-start outlier. |
| ETL/KPI correctness | — | 24 tests pass | MEASURED by `pytest tests/ -v` (CI gate). Correctness, not business latency. |

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
python -m pytest tests/ -v              # expect 24 passed
```