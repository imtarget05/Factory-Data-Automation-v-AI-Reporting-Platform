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
| **Deployment** | Docker, Docker Compose |

---

## 📊 Dataset | Dữ Liệu

**80,385 synthetic records** simulating 90 days of factory operations:

| Dataset | Records | Description |
|---------|---------|-------------|
| `production.csv` | 45,000 | Daily production by line, shift, product |
| `quality.csv` | 9,000 | Quality inspections, defect types, severity |
| `inventory.csv` | 900 | Stock levels, incoming/outgoing, reorder points |
| `machine.csv` | 18,000 | Machine status, temperature, vibration, downtime |
| `workers.csv` | 7,485 | Worker productivity, hours, defects caused |

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

# 4. Start Ollama (for local AI)
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

1. Click **"Generate Sample Data"** in the sidebar (or data is already generated)
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
python -m pytest tests/ -v
```

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
24 passed in 1.36s
```

All tests pass: ETL pipeline (12 tests) + KPI engine (12 tests).

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

## 📬 Contact | Liên Hệ

**English:** This project was developed as an internship portfolio project for AI & Data Automation.  
**Tiếng Việt:** Dự án này được phát triển như một sản phẩm portfolio thực tập về AI và Tự động hóa dữ liệu.

---

## 📄 License | Giấy Phép

MIT License — Free to use, modify, and distribute.# Factory-Data-Automation-v-AI-Reporting-Platform
