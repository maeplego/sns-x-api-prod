import asyncio
import logging

import structlog
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import settings
from app.core.queue import RedisEventBus, get_event_bus
from app.core.startup import verify_postgres, verify_redis
from app.labeling.dispatcher import dispatch_event, parse_stream_fields
from app.labeling.events import CONSUMER_GROUP, STREAM_KEY
from app.labeling.loading import load_all
from app.ranking.weights import load_weights

logger = structlog.get_logger(__name__)
logging.basicConfig(level=settings.log_level.upper())


async def run_worker(consumer_name: str = "worker-1", block_ms: int = 5000) -> None:
    load_all()
    load_weights()
    await verify_postgres()
    await verify_redis()

    bus = get_event_bus()
    if not isinstance(bus, RedisEventBus):
        raise RuntimeError("Worker requires RedisEventBus")

    await bus.ensure_group()
    client = bus._client
    logger.info("worker_started", stream=STREAM_KEY, group=CONSUMER_GROUP, consumer=consumer_name)

    while True:
        try:
            entries = await client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=consumer_name,
                streams={STREAM_KEY: ">"},
                count=10,
                block=block_ms,
            )
        except RedisTimeoutError:
            logger.warning("worker_read_timeout")
            continue
        except (RedisConnectionError, RedisError):
            logger.exception("worker_redis_unavailable")
            await asyncio.sleep(1)
            continue

        if not entries:
            continue

        for _stream, messages in entries:
            for message_id, fields in messages:
                try:
                    event_type, payload = parse_stream_fields(fields)
                    await dispatch_event(event_type, payload)
                    await client.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
                except Exception:
                    logger.exception("worker_message_failed", message_id=message_id)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
