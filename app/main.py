import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.middleware import RequestIdMiddleware
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
    muted_keywords,
    mutes,
    notifications,
    posts,
    search,
    under_the_hood,
    users,
)

logger = structlog.get_logger(__name__)


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
    title="sns-x-api",
    description="Product SNS forked from sns-tutorial-x-api (visibility labels, ranking, UTH)",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "2.0.0"}
