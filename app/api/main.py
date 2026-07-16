"""
FastAPI Backend for Smart Manufacturing Platform.
Provides REST API endpoints for data access and report generation.
"""
import os
import sys
import uuid
import time
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Dict, List, Optional
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.etl.pipeline import run_etl
from app.etl.kpi_engine import calculate_all_kpis
from app.reports.alert_system import AlertManager
from app.reports.exporter import ReportExporter
from app.ai.reporting import AIReportGenerator
from app.ai.marketing import MarketingGenerator
from app.utils.config import DATA_EXPORTS_DIR
from app.utils.logging_config import get_logger, log_event

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every HTTP request with correlation ID and latency for MLOps observability."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    start = time.time()
    logger.info(f"request_start", extra={
        "component": "api",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path
    })
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    logger.info(f"request_end", extra={
        "component": "api",
        "request_id": request_id,
        "status_code": response.status_code,
        "duration_ms": duration_ms
    })
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
            "export": "/api/v1/export"
        }
    }


@app.get("/api/v1/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "data_loaded": _datasets is not None
    }


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
            "data": df.head(100).to_dict(orient="records")
        }
    
    return {
        "datasets": {
            name: {"rows": len(df), "columns": list(df.columns)}
            for name, df in _datasets.items()
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
                "data": df.tail(30).to_dict(orient="records")
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
    
    return {
        "total": len(alert_dicts),
        "alerts": alert_dicts
    }


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
        "download_url": f"/api/v1/download/{os.path.basename(filepath)}"
    }


@app.get("/api/v1/download/{filename}")
async def download_file(filename: str):
    """Download an exported file."""
    filepath = os.path.join(DATA_EXPORTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "File not found")
    
    media_type = "application/pdf" if filename.endswith(".pdf") else \
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    return FileResponse(filepath, media_type=media_type, filename=filename)


@app.post("/api/v1/refresh")
async def refresh():
    """Force refresh all data."""
    success = refresh_data()
    return {
        "success": success,
        "message": "Data refreshed successfully" if success else "No data found"
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
        "datasets": {k: str(v.shape) for k, v in _datasets.items()}
    }
    response = ai_gen.chat_query(query, context)
    
    return {
        "query": query,
        "response": response,
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)