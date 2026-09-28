"""
FastAPI Backend for Smart Manufacturing Platform.
Provides REST API endpoints for data access and report generation.
"""

import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.security import ApiKeyMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai.marketing import MarketingGenerator
from app.ai.reporting import AIReportGenerator
from app.etl.kpi_engine import calculate_all_kpis
from app.etl.pipeline import run_etl
from app.reports.alert_system import AlertManager
from app.reports.exporter import ReportExporter
from app.utils.config import DATA_EXPORTS_DIR
from app.utils.logging_config import get_logger

logger = get_logger("api", "backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_data()
    yield


app = FastAPI(
    title="Smart Manufacturing Platform API",
    description="REST API for factory data automation and AI reporting",
    version="1.0.0",
    lifespan=lifespan,
)

def _allowed_origins() -> list[str]:
    raw = os.getenv("FACTORY_CORS_ORIGINS", "http://localhost:8501,http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiKeyMiddleware)


# --- Minimal Prometheus helper (additive; zero new dependencies) ----------------
# In-memory request counters + process start time for GET /metrics below.
# Unauthenticated (standard for Prometheus scraping). Does not alter any
# existing route, auth, or response shape.
_METRICS_START_TIME = time.time()
_http_requests_total: dict = {}


def _bump_http_counter(route: str, status: int) -> None:
    key = (route, str(status))
    _http_requests_total[key] = _http_requests_total.get(key, 0) + 1


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every HTTP request with correlation ID and latency for MLOps observability."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    start = time.time()
    logger.info(
        "request_start",
        extra={
            "component": "api",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        },
    )
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    _bump_http_counter(request.url.path, response.status_code)
    logger.info(
        "request_end",
        extra={
            "component": "api",
            "request_id": request_id,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


# Global cache
_datasets = None
_kpis = None
_alerts = None


def refresh_data():
    """Refresh cached data."""
    global _datasets, _kpis, _alerts
    _datasets = run_etl()
    if _datasets:
        _kpis = calculate_all_kpis(_datasets)
        alert_mgr = AlertManager()
        _alerts = alert_mgr.check_all(_datasets, _kpis)
    return _datasets is not None


@app.get("/")
async def root():
    return {
        "app": "Smart Manufacturing Platform",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "data": "/api/v1/data",
            "kpis": "/api/v1/kpis",
            "alerts": "/api/v1/alerts",
            "report": "/api/v1/report",
            "export": "/api/v1/export",
        },
    }


@app.get("/api/v1/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "data_loaded": _datasets is not None,
    }


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus text exposition (aggregate KPI gauges, no raw dataset rows)."""
    from fastapi.responses import PlainTextResponse

    up = 1 if _datasets is not None else 0
    n_alerts = len(_alerts) if _alerts else 0
    out = [
        "# HELP factory_data_up 1 if datasets loaded in memory.",
        "# TYPE factory_data_up gauge",
        f"factory_data_up {up}",
        "# HELP factory_alerts_active Current active alerts.",
        "# TYPE factory_alerts_active gauge",
        f"factory_alerts_active {n_alerts}",
        "# HELP factory_uptime_seconds Process uptime in seconds.",
        "# TYPE factory_uptime_seconds gauge",
        f"factory_uptime_seconds {time.time() - _METRICS_START_TIME:.2f}",
        "# HELP factory_http_requests_total Total HTTP requests by route and status.",
        "# TYPE factory_http_requests_total counter",
    ]
    for (route, status), count in sorted(_http_requests_total.items()):
        out.append(f'factory_http_requests_total{{route="{route}",status="{status}"}} {count}')
    if _kpis:
        for kpi in _kpis:
            name = str(getattr(kpi, "name", "")).replace('"', "")
            try:
                value = float(getattr(kpi, "value", 0.0))
            except (TypeError, ValueError):
                continue
            out.append(f'factory_kpi_value{{kpi="{name}"}} {value:g}')
    return PlainTextResponse("\n".join(out) + "\n", media_type="text/plain; version=0.0.4")


@app.get("/api/v1/data")
async def get_data(dataset: Optional[str] = None):
    """Get raw datasets."""
    if _datasets is None:
        if not refresh_data():
            raise HTTPException(404, "No data available")

    if dataset:
        if dataset not in _datasets:
            raise HTTPException(404, f"Dataset '{dataset}' not found")
        df = _datasets[dataset]
        return {
            "name": dataset,
            "rows": len(df),
            "columns": list(df.columns),
            "data": df.head(100).to_dict(orient="records"),
        }

    return {
        "datasets": {
            name: {"rows": len(df), "columns": list(df.columns)} for name, df in _datasets.items()
        }
    }


@app.get("/api/v1/kpis")
async def get_kpis():
    """Get all calculated KPIs."""
    if _kpis is None:
        if not refresh_data():
            raise HTTPException(404, "No data available")

    result = {}
    for name, df in _kpis.items():
        if isinstance(df, pd.DataFrame):
            result[name] = {
                "rows": len(df),
                "columns": list(df.columns),
                "latest": df.iloc[-1].to_dict() if not df.empty else None,
                "data": df.tail(30).to_dict(orient="records"),
            }
        elif isinstance(df, dict):
            result[name] = {
                k: v.to_dict(orient="records") if isinstance(v, pd.DataFrame) else v
                for k, v in df.items()
            }

    return result


@app.get("/api/v1/alerts")
async def get_alerts(level: Optional[str] = None):
    """Get active alerts."""
    if _alerts is None:
        if not refresh_data():
            raise HTTPException(404, "No data available")

    alert_dicts = [a.to_dict() for a in _alerts]

    if level:
        alert_dicts = [a for a in alert_dicts if a["level"] == level.upper()]

    return {"total": len(alert_dicts), "alerts": alert_dicts}


@app.get("/api/v1/report")
async def generate_report():
    """Generate AI report."""
    if _datasets is None or _kpis is None:
        if not refresh_data():
            raise HTTPException(404, "No data available")

    alert_dicts = [a.to_dict() for a in _alerts] if _alerts else []
    ai_gen = AIReportGenerator()
    report = ai_gen.generate_report(_kpis, alert_dicts, _datasets)

    return report


@app.get("/api/v1/export")
async def export_report(format: str = Query("excel", pattern="^(excel|pdf|all)$")):
    """Export report to Excel or PDF."""
    if _datasets is None or _kpis is None:
        if not refresh_data():
            raise HTTPException(404, "No data available")

    alert_dicts = [a.to_dict() for a in _alerts] if _alerts else []
    exporter = ReportExporter()
    ai_gen = AIReportGenerator()
    ai_report = ai_gen.generate_report(_kpis, alert_dicts, _datasets)

    if format == "excel":
        filepath = exporter.export_to_excel(_kpis, alert_dicts)
    elif format == "pdf":
        filepath = exporter.export_to_pdf(_kpis, alert_dicts, ai_report)
    else:
        result = exporter.export_all(_kpis, alert_dicts, ai_report)
        return result

    return {
        "filepath": filepath,
        "filename": os.path.basename(filepath),
        "download_url": f"/api/v1/download/{os.path.basename(filepath)}",
    }


@app.get("/api/v1/download/{filename}")
async def download_file(filename: str):
    """Download an exported file."""
    filepath = os.path.join(DATA_EXPORTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "File not found")

    media_type = (
        "application/pdf"
        if filename.endswith(".pdf")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    return FileResponse(filepath, media_type=media_type, filename=filename)


@app.post("/api/v1/refresh")
async def refresh():
    """Force refresh all data."""
    success = refresh_data()
    return {
        "success": success,
        "message": "Data refreshed successfully" if success else "No data found",
    }


@app.get("/api/v1/marketing")
async def generate_marketing(
    product_name: str = Query("Giày thể thao cao cấp", description="Tên sản phẩm"),
    product_info: str = Query("", description="Thông tin thêm về sản phẩm"),
):
    """Generate AI marketing content (Facebook post, email, product description)."""
    gen = MarketingGenerator()
    result = gen.generate_all(product_name, product_info)
    return result


@app.get("/api/v1/chat")
async def chat(query: str = Query(..., description="Your question about factory data")):
    """AI Chat endpoint."""
    if _datasets is None or _kpis is None:
        if not refresh_data():
            raise HTTPException(404, "No data available")

    ai_gen = AIReportGenerator()
    context = {
        "kpis": {k: str(v) for k, v in _kpis.items()},
        "datasets": {k: str(v.shape) for k, v in _datasets.items()},
    }
    response = ai_gen.chat_query(query, context)

    return {"query": query, "response": response, "timestamp": datetime.now().isoformat()}


# --- FDA-021-025: POST /api/v1/query (additive; no existing route touched) ----
# Executes a read-only sql_tool JSON spec over the computed KPI frames.
# Guardrails: validate_spec allow-list (incl. explicit SELECT-only /
# DELETE/DROP rejection), top_n capped at MAX_ROWS, all spec errors -> 422
# JSON (never 500 on a bad spec).


@app.post("/api/v1/query")
async def post_query(body: dict):
    """Run an ad-hoc read-only aggregation spec over the KPI frames.

    Body: either the spec itself or ``{"spec": {...}, "timeout": secs}``.
    ``timeout`` is clamped to [1, 30]s and bounds only this request's
    execution; ``top_n`` is capped by ``validate_spec`` at ``MAX_ROWS``.
    """
    from app.ai.sql_tool import MAX_ROWS, _resolve_frames, execute_spec

    if not isinstance(body, dict):
        raise HTTPException(422, "spec must be an object")
    spec = body.get("spec", body) if "spec" in body or "frame" not in body else body
    if not isinstance(spec, dict):
        raise HTTPException(422, "spec must be an object")
    try:
        timeout = int(body.get("timeout", 30)) if "spec" in body else 30
    except (TypeError, ValueError):
        raise HTTPException(422, "timeout must be an integer")
    timeout = max(1, min(timeout, 30))

    if _kpis is None:
        if not refresh_data():
            raise HTTPException(404, "No data available")
    frames = _resolve_frames(_kpis)
    if not frames:
        raise HTTPException(422, "no KPI frames available")

    import time as _time

    start = _time.time()
    try:
        rows = execute_spec(spec, frames)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:  # never leak a 500 for a bad spec
        raise HTTPException(422, f"spec failed: {type(exc).__name__}")
    elapsed = _time.time() - start
    if elapsed > timeout:
        raise HTTPException(422, f"query exceeded timeout of {timeout}s")
    rows = rows[:MAX_ROWS]
    return {"rows": rows, "count": len(rows), "spec": spec}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
