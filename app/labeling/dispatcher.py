import json

import structlog

from app.labeling.context import TaskContext
from app.labeling.flows.post_publish.tasks import MarkFailedPostTask
from app.labeling.loading import get_plans_for_event

logger = structlog.get_logger(__name__)


async def dispatch_event(event_type: str, payload: dict) -> bool:
    plans = get_plans_for_event(event_type)
    if not plans:
        logger.warning("no_plan_for_event", event_type=event_type)
        return False

    ctx = TaskContext(event_type=event_type, payload=payload)
    success = True
    for plan in plans:
        ok = await plan.execute(ctx)
        success = success and ok

    if not success:
        fail_ctx = TaskContext(event_type=event_type, payload=payload, errors=ctx.errors)
        await MarkFailedPostTask.exec(fail_ctx)
        logger.error("event_processing_failed", event_type=event_type, errors=ctx.errors)
    else:
        logger.info(
            "event_processed",
            event_type=event_type,
            payload=payload,
            plans=[plan.KEY for plan in plans],
        )

    return success


def parse_stream_fields(fields: dict[str, str]) -> tuple[str, dict]:
    event_type = fields["event_type"]
    payload = json.loads(fields["payload"])
    return event_type, payload
