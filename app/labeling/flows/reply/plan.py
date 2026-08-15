from app.core.registry import register
from app.labeling.events import POST_CREATED
from app.labeling.flows.reply.tasks import (
    IncrementReplyCountTask,
    IncrementRepostCountTask,
    NotifyReplyTask,
    NotifyRepostTask,
)
from app.labeling.plan import run_plan
from app.labeling.registry import Plan


@register
class ReplySideEffectsPlan(Plan):
    KEY = "reply_side_effects"
    EVENT_TYPES = [POST_CREATED]
    ORDER = 75

    TASKS = {
        "reply_count": IncrementReplyCountTask,
        "notify": NotifyReplyTask,
        "repost_count": IncrementRepostCountTask,
        "notify_repost": NotifyRepostTask,
    }

    TASK_DEPENDENCIES = {
        "reply_count": set(),
        "notify": set(),
        "repost_count": set(),
        "notify_repost": set(),
    }

    async def execute(self, ctx) -> bool:
        return await run_plan(self.TASKS, self.TASK_DEPENDENCIES, ctx)
