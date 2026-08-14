import json
from abc import ABC, abstractmethod

import redis.asyncio as redis

from app.core.config import settings
from app.labeling.events import CONSUMER_GROUP, STREAM_KEY


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event_type: str, payload: dict) -> str: ...


class RedisEventBus(EventBus):
    def __init__(self) -> None:
        # redis-py 6 defaults socket_timeout to 5s. XREADGROUP block must exceed that
        # or the idle worker dies and posts stay in `processing`.
        self._client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=None,
            health_check_interval=0,
        )

    async def ensure_group(self) -> None:
        try:
            await self._client.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, event_type: str, payload: dict) -> str:
        message_id = await self._client.xadd(
            STREAM_KEY,
            {
                "event_type": event_type,
                "payload": json.dumps(payload),
            },
        )
        return message_id


class InlineEventBus(EventBus):
    """Process events synchronously — used in tests."""

    async def publish(self, event_type: str, payload: dict) -> str:
        from app.labeling.dispatcher import dispatch_event

        await dispatch_event(event_type, payload)
        return "inline-0"

    async def ensure_group(self) -> None:
        return


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        if settings.app_env == "test":
            _event_bus = InlineEventBus()
        else:
            _event_bus = RedisEventBus()
    return _event_bus


def set_event_bus(bus: EventBus | None) -> None:
    global _event_bus
    _event_bus = bus
