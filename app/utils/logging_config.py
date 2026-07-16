"""
Structured logging configuration for MLOps observability.
Logs are emitted in JSON format with request correlation for easy aggregation.
"""
import json
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any


class JsonFormatter(logging.Formatter):
    """Format log records as JSON with structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if hasattr(record, "component"):
            log_entry["component"] = record.component
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def get_logger(name: str = "factory_platform", component: str = "app") -> logging.LoggerAdapter:
    """Return a configured logger adapter with component tagging."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    adapter = logging.LoggerAdapter(logger, {"component": component})
    return adapter


def log_event(logger: logging.LoggerAdapter, event: str, level: int = logging.INFO, **kwargs) -> None:
    """Helper to log a structured event with extra fields."""
    extra = {"component": kwargs.pop("component", "app")}
    logger.log(level, f"{event}", extra=extra)
    if kwargs:
        logger.log(level, json.dumps(kwargs, ensure_ascii=False, default=str), extra=extra)
