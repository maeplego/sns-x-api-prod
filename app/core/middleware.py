import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.metrics import ERRORS, LATENCY, REQUESTS, normalize_path

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

# Legacy counters kept for compatibility with older dashboards/tests.
requests_total = 0
errors_total = 0


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        global requests_total, errors_total

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_ctx.set(request_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        path = normalize_path(request.url.path)
        method = request.method
        started = time.perf_counter()
        requests_total += 1
        response = await call_next(request)
        elapsed = time.perf_counter() - started

        status = str(response.status_code)
        REQUESTS.labels(method=method, path=path, status=status).inc()
        LATENCY.labels(method=method, path=path).observe(elapsed)
        if response.status_code >= 500:
            errors_total += 1
            ERRORS.labels(method=method, path=path).inc()

        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline browser hardening headers (reverse proxies may add HSTS at the edge)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if settings.app_env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
