"""Minimal API-key guard for Factory API (Phase 0 trust fix).

Pattern copied from CreditFlow/backend/security.py but simplified:
- single shared secret via env FACTORY_API_KEY
- open mode when env empty (local dev/demo), enforced when set
- skips safe paths: /, /api/v1/health, /metrics, /docs, /openapi.json
- Prometheus /metrics stays open by design (scraper has no key)
"""

import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

SAFE_PREFIXES = ("/api/v1/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/favicon.ico")
SAFE_EXACT = {"/"}


def configured_api_key() -> str:
    return os.getenv("FACTORY_API_KEY", "").strip()


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        expected = configured_api_key()
        if not expected:
            return await call_next(request)  # local dev open mode
        path = request.url.path
        if path in SAFE_EXACT or path.startswith(SAFE_PREFIXES):
            return await call_next(request)
        provided = request.headers.get("X-Factory-API-Key", "")
        if provided and secrets.compare_digest(provided, expected):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={"detail": "missing or invalid X-Factory-API-Key"},
        )
