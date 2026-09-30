# 🏭 Smart Manufacturing Platform — AI-Powered Factory Data Automation

[![Python](https://img.shields.io/badge/Python-3.9+-blue)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.50+-red)](https://streamlit.io)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128+-green)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/LLM-Qwen2.5_3B-orange)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 📋 Project Overview | Tổng Quan Dự Án

**English:**  
An AI-powered data automation and intelligent reporting system for manufacturing operations. This project simulates a shoe factory and automates the entire data pipeline — from raw Excel/CSV files to interactive dashboards, AI-generated executive reports, and automated alerts — replacing manual copy-paste, filtering, merging, pivot tables, charting, and report writing.

**Tiếng Việt:**  
Hệ thống tự động hóa dữ liệu có hỗ trợ bởi AI và báo cáo thông minh cho hoạt động sản xuất. Dự án mô phỏng một nhà máy sản xuất giày và tự động hóa toàn bộ quy trình xử lý dữ liệu — từ file Excel/CSV thô đến bảng điều khiển tương tác, báo cáo điều hành do AI tạo ra, và cảnh báo tự động — thay thế hoàn toàn việc copy-paste, lọc, merge, pivot, vẽ biểu đồ và viết báo cáo thủ công.

---

## 🎯 Key Features | Tính Năng Chính

### 8 Modules | 8 Mô-đun

| # | Module | Description | Mô tả |
|---|--------|-------------|-------|
| 1 | **Data Import** | Auto-detect CSV/Excel files in `data/raw/` | Tự động phát hiện file CSV/Excel |
| 2 | **Data Cleaning** | Remove duplicates, fill missing, validate, convert datetime | Xóa trùng, điền thiếu, kiểm tra lỗi |
| 3 | **KPI Engine** | 84+ KPIs: OEE, Reject Rate, Yield, Machine Utilization, etc. | Tính 84+ chỉ số KPI sản xuất |
| 4 | **Dashboard** | 9 Streamlit pages with Plotly interactive charts | 9 trang dashboard với biểu đồ tương tác |
| 5 | **AI Reporting** | Local Qwen2.5 generates Summary, Problems, Recommendations, Risks | AI tạo báo cáo: Tóm tắt, Vấn đề, Đề xuất, Rủi ro |
| 6 | **Export** | One-click Excel (multi-sheet) + PDF (professional report) | Xuất Excel nhiều sheet + PDF chuyên nghiệp |
| 7 | **Alert System** | Reject>5%→Warning, Inventory<200→Alert, Downtime>30min→Alert | Cảnh báo tự động theo ngưỡng |
| 8 | **AI Chat** | Ask questions: "Which machine has highest downtime?" | Hỏi đáp với dữ liệu nhà máy |

---

## 🏗️ Architecture | Kiến Trúc

```
Excel / CSV Files
       │
       ▼
Python ETL Pipeline (Pandas + Polars)
       │
       ▼
Data Cleaning & Validation
       │
       ▼
KPI Calculation Engine
       │
   ┌───┴───┐
   ▼       ▼
Dashboard  AI Report (Local Qwen2.5)
   ▼       ▼
Charts     Executive Summary / Problems / Recommendations / Risks
   │       │
   └───┬───┘
       ▼
Export PDF / Excel + Email Alerts
```

---

## 🛠️ Tech Stack | Công Nghệ

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.9+ |
| **Data Processing** | Pandas, Polars, OpenPyXL |
| **Dashboard** | Streamlit, Plotly, Altair, Streamlit-Aggrid |
| **Backend API** | FastAPI, Uvicorn |
| **Database** | SQLAlchemy, SQLite |
| **AI / LLM** | Ollama + Qwen2.5:3b (local, zero API cost) |
| **Export** | ReportLab (PDF), OpenPyXL (Excel) |
| **Scheduler** | APScheduler |
| **Deployment** | Docker, Docker Compose, Azure Container Apps |

---

## ☁️ Live Deployment | Triển khai Thật

The API is deployed to Azure Container Apps and verified by probing the live
endpoint, not by reading a config file.

**Live URL:** https://ca-factory-api.wittysand-b748274c.eastasia.azurecontainerapps.io

Three identities are tracked separately, because they answer different
questions and a change to documentation does not move the deployed artifact:

| Identity | Value | Means |
|---|---|---|
| **Source** | `4e4e8b58d0551a080ea6750deb3f2a1ce9c98265` | the commit the running image was built from |
| **Artifact** | `sha256:675fd4f2782308fb2779d29130cdd17006bc449958613d6fc023d3c31c5728f2` | OCI digest of the pushed image (buildx attestation) |
| **Runtime** | revision `ca-factory-api--0000001`, traffic weight 100 | the revision actually serving traffic |

The chain is: commit → CI build provenance → image digest → Azure revision →
runtime probes. The commit is not a hash of the digest and must not be read as
one; the provenance attestation is what links them.

### Runtime verification (probed against the live URL, 2026-09-30)

| Endpoint | Result |
|---|---|
| `/api/v1/health` | 200 `{"status":"healthy","data_loaded":true}` |
| `/api/v1/data` | 200, 5 datasets, 26 132 rows |
| `/api/v1/kpis` | 200, `daily_production` 90 rows |
| `/api/v1/report` | 200, executive summary |
| `/metrics` | 200, `factory_data_up 1` |
| `/metrics-evil` | 404 — the safe-path matcher is exact-or-boundary, so a prefix-looking path is not treated as open |

**The deployed revision predates the quality gate.** The live `/api/v1/report`
returns `title/date/summary/key_metrics/problems/recommendations/risks/root_causes`
and **no** `generation_mode`, `quality`, `evidence` or `provenance` keys. The gate
is committed to the working tree and tested locally; shipping it to Azure is a
separate step (see *Known gaps* below). Verification here means "the running image
is the commit named above", not "the running image is the working tree".

### A deployment bug worth reading about

This service previously reported itself healthy while every business endpoint
returned 500. `data/raw/*` is gitignored, so an image built from a clean clone
shipped an empty `data/`. `refresh_data()` produced `{}`, and
`_datasets is not None` was **True for an empty dict** — so `/api/v1/health`
said `data_loaded: true`, `factory_data_up` was 1, and `/api/v1/data` answered
200 with `{"datasets": {}}`. Only the KPI, alerts and report endpoints failed,
loudly, on top of a green health check.

Three changes closed it:

1. `data_is_loaded()` checks for a non-empty load. Health returns **503 /
   degraded** when no data is loaded, so the container `HEALTHCHECK` now fails
   an empty deployment instead of passing it.
2. Business endpoints return **503 naming `data/raw`** rather than raising 500
   or answering 200 with an empty payload.
3. The image generates its own fixture at build time and asserts
   `data/raw/*.csv` is non-empty, so a silently empty image fails the build.

`tests/test_api_deployment_integrity.py` pins both directions. Reverting
`data_is_loaded()` to `is not None` fails 9 of its 16 tests, and deleting the
CSVs from a running container flips Docker's healthcheck to `unhealthy`. A CI
job (`container-smoke`) builds the image from a clean clone and calls the
business endpoints, because the 242-test suite could not catch this: it
generates data *before* pytest runs, so the working tree always had CSVs.

Full write-up: `docs/evidence/factory_p1_triage.md` in the workspace.

### Data-quality gate for AI reporting (Phase C)

The AI report is only trustworthy if the numbers it narrates are trustworthy. A
deterministic gate — not the model, not the dashboard — decides whether
reporting may run at all:

```
raw CSV → ETL → row contracts ──violating rows──▶ quarantine DLQ
                     │                              │
                     ▼                              ▼
              KPI engine ──────────────▶ evaluate_quality(datasets, kpis, quarantine)
                                                │
                        ┌───────────────────────┼───────────────────────┐
                     GOOD                   BAD / UNKNOWN          (never inferred)
                        │                       │                       │
                        ▼                       ▼                       ✗
              REAL_MODEL or FALLBACK      generation_mode            LLM
              (evidence snapshot id)     = "NOT_RUN", 0 calls       unreachable
```

- `GOOD` / `BAD` / `UNKNOWN` — `UNKNOWN` is a real outcome, never rounded down to
  "probably fine". Missing datasets or an uncomputable check produce `UNKNOWN`,
  which blocks.
- **Fail-closed**: `BAD` and `UNKNOWN` both return a well-formed report with
  `status: "BLOCKED"`, `generation_mode: "NOT_RUN"`, empty `provenance` and
  `evidence: null`. Zero LLM calls — asserted at unit *and* HTTP level.
- **Honest generation modes**: `REAL_MODEL` (LLM answered), `FALLBACK`
  (deterministic data-driven text — never mislabelled as model output),
  `NOT_RUN` (blocked).
- **Evidence is the source of truth, not the narrative.** `evidence.kpis` is
  built from the frames themselves and carries a `snapshot_id`
  (`snap-` + sha256 of the canonical KPI+sources JSON). Same inputs ⇒ same id.
  NaN/±inf are coerced to `null` so no non-standard JSON token escapes.
- **Provenance is checked, not trusted.** Any id a narrative cites must exist in
  `evidence.source_ids`; fabricated ids are dropped and counted in
  `provenance_rejected`. A deterministic fallback cites nothing, which is not a
  violation — it scores 0.
- **The quarantine DLQ feeds the gate.** `_quality_context()` in `app/api/main.py`
  turns the row-level gate's DLQ into gate input, so a batch that is mostly
  quarantined cannot authorize a report.
- **Auditability through the existing logger**: `quality_gate_decision`,
  `report_blocked`, `report_provenance` and `data_driven_report` events, all via
  `log_event`. No parallel logging framework.

Mutation controls `M1`–`M4` (`tests/test_ai_quality_mutations.py`) monkeypatch
each check into a no-op and assert the gate tests then fail. They are marked
`xfail` on purpose: they must never pass, and if one *does* pass, the mutation
was not actually neutralized.

### Known gaps | Khoảng trống đã biết

- The Azure revision `ca-factory-api--0000001` (commit `4e4e8b58`) does **not**
  contain the quality gate; the live report response has no
  `generation_mode`/`quality`/`evidence` keys. Deploying the gate is the next step.
- `FACTORY_API_KEY` is not set in the deployed container, so the API-key
  middleware is in documented open mode there. The middleware's enforced path is
  covered by `tests/test_api_key_auth.py`, but production enforcement requires the
  secret to be provisioned.
- No alerting is wired from the block path to an external channel yet; block
  events exist only in the application log.

---

## 📊 Dataset | Dữ Liệu

**26,119 synthetic records** simulating 90 days of factory operations (as produced by `python -m scripts.generate_sample_data`, seed 42):

| Dataset | Records | Description |
|---------|---------|-------------|
| `production.csv` | 11,271 | Daily production by line, shift, product |
| `quality.csv` | 3,636 | Quality inspections, defect types, severity |
| `inventory.csv` | 909 | Stock levels, incoming/outgoing, reorder points |
| `machine.csv` | 5,454 | Machine status, temperature, vibration, downtime |
| `workers.csv` | 4,849 | Worker productivity, hours, defects caused |

---

## 🚀 Quick Start | Bắt Đầu Nhanh

### Prerequisites | Yêu Cầu

- Python 3.9+
- [Ollama](https://ollama.com) (for local AI)

### Installation | Cài Đặt

```bash
# 1. Clone the project
cd "Factory Data Automation & AI Reporting Platform"

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate the deterministic sample data (REQUIRED on a fresh clone:
#    data/raw/*.csv is gitignored, so a new clone contains no input data)
python -m scripts.generate_sample_data

# 5. Start Ollama (for local AI)
brew services start ollama
ollama pull qwen2.5:3b  # First time only (1.9GB)
```

### Run | Chạy

```bash
# Launch the dashboard
streamlit run app/dashboard/run.py --server.port=8501
```

Open **http://localhost:8501** in your browser.

### Steps | Các Bước

1. Run `python -m scripts.generate_sample_data` once after cloning, or click **"Generate Sample Data"** in the sidebar. `data/raw/*.csv` is gitignored, so a fresh clone has no data until you do this.
2. Click **"Load / Refresh Data"**
3. Explore the **9 dashboard pages**
4. Click **"Generate New Report"** for AI executive summary
5. Ask questions in **AI Chat**
6. **Export** reports with one click

### Run API | Chạy API

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

API docs at **http://localhost:8000/docs**

### Run Tests | Chạy Kiểm Thử

```bash
python -m pytest tests/ -q
```

**Verified: 288 passed, 5 skipped, 4 xfailed** on the working tree
(`4e4e8b58` + Phase C quality gate). The 4 `xfailed` are the mutation-detection
controls `M1`–`M4` in `tests/test_ai_quality_mutations.py` — they are *supposed*
to fail, and passing-by-failure is how they prove the gate tests detect a
neutralized check. If `258 passed, 5 skipped` (commit `4e4e8b5`) is what you see,
you are on the pre-Phase-C tree.
If `data/raw/` is empty, run `python -m scripts.generate_sample_data` first —
`tests/conftest.py` also falls back to a stdlib seed, but that smaller dataset
is not what the numbers above were measured on.

---

## 📁 Project Structure | Cấu Trúc Dự Án

```
smart-manufacturing-platform/
├── app/
│   ├── api/          # FastAPI REST API
│   ├── etl/          # ETL Pipeline + KPI Engine
│   │   ├── pipeline.py      # Data import & cleaning
│   │   ├── polars_etl.py    # Polars high-performance ETL
│   │   └── kpi_engine.py    # KPI calculations
│   ├── dashboard/    # Streamlit dashboard (9 pages)
│   │   └── run.py           # Main dashboard app
│   ├── ai/           # AI modules
│   │   ├── local_llm.py     # Ollama + Qwen2.5 interface
│   │   └── reporting.py     # AI report & chat generation
│   ├── reports/      # Export & alerts
│   │   ├── exporter.py      # PDF/Excel export
│   │   ├── alert_system.py  # Alert detection
│   │   └── email_simulator.py # Email alert simulation
│   ├── scheduler/    # APScheduler automation
│   │   └── tasks.py         # Scheduled tasks
│   ├── database/     # SQLAlchemy models
│   │   └── models.py        # DB schema
│   └── utils/        # Configuration & data generation
│       ├── config.py        # Settings
│       └── data_generator.py # Synthetic data generator
├── data/
│   ├── raw/          # Raw CSV/Excel files
│   ├── processed/    # Cleaned parquet files
│   └── exports/      # Generated reports
├── tests/            # Pytest test suite
│   ├── test_etl.py   # ETL tests
│   └── test_kpi.py   # KPI tests
├── docker/           # Docker configuration
│   ├── Dockerfile
│   └── docker-compose.yml
├── .env              # Environment variables
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

---

## 🔧 Configuration | Cấu Hình

Edit `.env` file:

```env
# AI Provider — Local Qwen2.5 (default, zero cost)
AI_PROVIDER=local
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_BASE_URL=http://localhost:11434

# Or switch to cloud APIs (requires API keys)
# AI_PROVIDER=gemini
# GEMINI_API_KEY=your_key_here

# Database
DATABASE_URL=sqlite:///data/manufacturing.db

# Factory Settings
FACTORY_NAME=Smart Factory Alpha
```

---

## 🧪 Test Results | Kết Quả Kiểm Thử

```
288 passed, 5 skipped, 4 xfailed
```

The 4 `xfailed` are mutation controls (`M1`–`M4`), not flaky tests — see
*Data-quality gate for AI reporting*.

**Reproduce:** `python -m pytest tests/ -q` — measured on the working tree at
`4e4e8b58` + Phase C, from a clean checkout, with the blessed fixture:

```
python -m scripts.verify_fixture --blessed docs/expected/factory-fixture.json
FIXTURE VERIFY: PASS  seed=42 days=90 datasets=5 total_rows=26119
```

The 5 skips are conditional (absent optional deps). Coverage spans ETL, KPI
engine, quarantine, contracts, query API, SQL tooling, parity/perf, API-key
auth, and deployment-integrity regression tests.

Note: the generator needs `faker`, which is declared in `requirements.txt:13`
but is deliberately *not* in `requirements.api.txt` — the API image installs it
only for the build-time fixture step and removes it in the same layer.

---

## 📈 Dashboard Pages | Các Trang Dashboard

| Page | Content |
|------|---------|
| **📊 Overview** | Today's Output, Achievement, Reject Rate, OEE, Production Trend, Alerts, Machine Status |
| **🏭 Production** | By Line, By Product, Shift Performance, Filters |
| **✅ Quality** | Pareto Chart, Severity Distribution, Defect Trend, Heatmap |
| **📦 Inventory** | Stock Trend, Stock by Product, ABC Analysis, Reorder Alerts |
| **🔧 Machine** | Status Cards, Utilization, Downtime, Temperature, Vibration, OEE |
| **🤖 AI Report** | Executive Summary, Key Metrics, Problems, Root Causes, Recommendations, Risks |
| **💬 AI Chat** | Ask questions about factory data |
| **📥 Export** | One-click Excel + PDF download |
| **🗄️ Data** | Raw data viewer with column info |

---

## 🔬 MLOps & Observability

### Structured Logging (JSON)
All API requests and ETL operations emit structured JSON logs with request correlation IDs for easy aggregation and debugging.

```json
{"timestamp": "2026-07-16T10:30:00Z", "level": "INFO", "logger": "api", "message": "request_end", "request_id": "a1b2c3d4", "status_code": 200, "duration_ms": 45.23}
```

### CI/CD Pipeline (GitHub Actions)
Automated pipeline runs on every push/PR to `main`:

| Stage | Description |
|-------|-------------|
| **Lint** | Ruff linter + format check |
| **Test** | Pytest with coverage report (uploaded to Codecov) |
| **Security** | Safety (dependency vulnerabilities) + Bandit (code security) |
| **Docker** | Build & cache Docker image (on main branch only) |

Workflow: `.github/workflows/ci.yml`

### AI Report Metrics
Every AI report generation is logged with:
- LLM model used (qwen2.5)
- Inference duration (ms)
- Fallback vs AI-generated status
- Alert count and severity breakdown

### Run CI Locally
```bash
# Lint
ruff check app/ tests/
ruff format --check app/ tests/

# Test with coverage
python -m pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## 🤖 AI Tools Integration | Tích Hợp Công Cụ AI

This project was developed with heavy use of modern AI tools to accelerate development and improve code quality.

| Tool | How it was used | Specific prompts / usage |
|------|----------------|-------------------------|
| **ChatGPT (GPT-4o)** | Generated synthetic factory data logic, wrote ETL pipeline code, designed KPI formulas | *"Generate 80k records of synthetic shoe factory production data with 5 CSV tables"*, *"Write a Python KPI engine that calculates OEE, yield, reject rate, machine utilization"* |
| **GitHub Copilot** | Code completion for Streamlit dashboard pages, FastAPI endpoints, test cases | Auto-completed Plotly chart configurations, Streamlit layout code, pytest fixtures |
| **Claude (Anthropic)** | Designed system architecture, wrote documentation, reviewed code quality, created README | *"Design an architecture for an AI-powered factory data automation system"*, *"Review this ETL pipeline for edge cases and performance issues"* |
| **GenAI Tools (LLM Router Design)** | Architected the multi-provider LLM routing strategy (local Qwen2.5 + optional Gemini fallback) | *"Design a fallback strategy for local LLM when it fails to generate structured reports"* |

### Example: ChatGPT Prompt for KPI Engine
```
Prompt: "Write Python code for a manufacturing KPI engine that calculates:
- OEE = Availability × Performance × Quality
- Reject Rate = (Defects / Total Produced) × 100
- Yield = Good Products / Total Products
- Machine Utilization = Running Time / Available Time

Input: pandas DataFrame with columns [line, shift, target, produced, defects, downtime_min]
Output: DataFrame with daily KPIs grouped by line and shift"
```

### Example: Copilot in Action
```python
# Copilot auto-completed this entire Plotly chart function
def create_oee_trend_chart(df):
    fig = px.line(
        df, x="date", y="oee", color="line",
        title="OEE Trend by Production Line",
        labels={"oee": "OEE (%)", "date": "Date"},
    )
    fig.add_hline(y=0.85, line_dash="dash", line_color="green",
                  annotation_text="World Class (85%)")
    return fig
```

> 💡 **Takeaway**: AI tools reduced development time by ~60%. Copilot handled boilerplate code, ChatGPT generated complex algorithms, and Claude reviewed architecture decisions.

## 📬 Contact | Liên Hệ

**English:** This project was developed as an internship portfolio project for AI & Data Automation.  
**Tiếng Việt:** Dự án này được phát triển như một sản phẩm portfolio thực tập về AI và Tự động hóa dữ liệu.

---

## 📄 License | Giấy Phép

MIT License — Free to use, modify, and distribute.# Factory-Data-Automation-v-AI-Reporting-Platform
