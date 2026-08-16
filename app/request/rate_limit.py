from collections.abc import Callable
from typing import Any

import redis.asyncio as redis
import structlog
from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.models import User
from app.request.auth import get_current_user

logger = structlog.get_logger(__name__)


async def _incr_with_expire(key: str, window_seconds: int) -> int | None:
    client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
        return int(count)
    except Exception as exc:  # noqa: BLE001 — fail-open on Redis errors
        logger.warning("rate_limit_redis_error", error=str(exc), key=key)
        return None
    finally:
        await client.aclose()


def rate_limit(
    action: str,
    *,
    limit: int,
    window_seconds: int = 60,
    per_user: bool = False,
) -> Callable:
    async def _check(request: Request, user: User | None) -> None:
        if settings.app_env == "test":
            return

        if per_user:
            if user is None:
                return
            identity = str(user.id)
        else:
            client = request.client.host if request.client else "unknown"
            identity = client

        key = f"rl:{action}:{identity}"
        count = await _incr_with_expire(key, window_seconds)
        if count is None:
            return
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )

    if per_user:

        async def _per_user(
            request: Request,
            current_user: User = Depends(get_current_user),
        ) -> None:
            await _check(request, current_user)

        return _per_user

    async def _per_ip(request: Request) -> None:
        await _check(request, None)

    return _per_ip


# Convenience dependencies
rate_limit_login: Any = Depends(rate_limit("login", limit=10, window_seconds=60))
rate_limit_signup: Any = Depends(rate_limit("signup", limit=5, window_seconds=60))
rate_limit_post: Any = Depends(rate_limit("post", limit=30, window_seconds=60, per_user=True))
