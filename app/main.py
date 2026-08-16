import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.database import engine
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware, errors_total, requests_total
from app.core.startup import run_startup_checks
from app.labeling.loading import load_all
from app.ranking.weights import load_weights
from app.request.feed.router import router as feed_router
from app.request.routers import (
    auth,
    blocks,
    feedback,
    follows,
    likes,
    moderation,
    muted_keywords,
    mutes,
    notifications,
    posts,
    reports,
    search,
    under_the_hood,
    users,
)

logger = structlog.get_logger(__name__)

APP_VERSION = "3.0.0"
_is_production = settings.app_env == "production"


def configure_logging() -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(
        "startup",
        app_env=settings.app_env,
        postgres_host=settings.postgres_host,
        redis_host=settings.redis_host,
    )
    if settings.app_env != "test":
        load_weights()
        load_all()
        await run_startup_checks()
    yield
    logger.info("shutdown")


app = FastAPI(
    title="sns-x-api-prod",
    description="Production-oriented fork of sns-x-api (auth hardening, RBAC, moderation)",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if _is_production and settings.allowed_host_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)

app.include_router(feed_router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(likes.router)
app.include_router(feedback.router)
app.include_router(notifications.router)
app.include_router(blocks.router)
app.include_router(mutes.router)
app.include_router(muted_keywords.router)
app.include_router(follows.router)
app.include_router(search.router)
app.include_router(under_the_hood.router)
app.include_router(reports.router)
app.include_router(moderation.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


@app.get("/health/ready")
async def health_ready() -> JSONResponse:
    errors: list[str] = []
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"postgres: {exc}")

    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        pong = await client.ping()
        if not pong:
            errors.append("redis: ping failed")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"redis: {exc}")
    finally:
        await client.aclose()

    if errors:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "errors": errors, "version": APP_VERSION},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "version": APP_VERSION},
    )


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    body = (
        f"requests_total {requests_total}\n"
        f"errors_total {errors_total}\n"
    )
    return PlainTextResponse(body)
