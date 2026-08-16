import redis.asyncio as redis
import structlog
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

logger = structlog.get_logger(__name__)


def assert_production_secrets() -> None:
    """Reject known-weak secrets when running as production."""
    if settings.app_env != "production":
        return
    if settings.is_weak_jwt_secret:
        raise RuntimeError(
            "Unsafe JWT_SECRET for production: use a random secret of at least 32 characters"
        )
    if settings.is_weak_postgres_password:
        raise RuntimeError("Unsafe POSTGRES_PASSWORD for production")


async def verify_postgres() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("postgres_ready", host=settings.postgres_host)


async def verify_redis() -> None:
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        pong = await client.ping()
        if not pong:
            raise RuntimeError("Redis ping returned falsy response")
    finally:
        await client.aclose()
    logger.info("redis_ready", host=settings.redis_host)


async def run_startup_checks() -> None:
    """Fail-fast: refuse to serve if secrets/deps are unsafe or unavailable."""
    assert_production_secrets()
    await verify_postgres()
    await verify_redis()
