from app.core.registry import register
from app.labeling.events import POST_CREATED
from app.labeling.flows.fanout.tasks import FanOutTask
from app.labeling.plan import run_plan
from app.labeling.registry import Plan


@register
class FanOutPlan(Plan):
    KEY = "fanout"
    EVENT_TYPES = [POST_CREATED]
    ORDER = 50

    TASKS = {
        "fanout": FanOutTask,
    }

    TASK_DEPENDENCIES = {
        "fanout": set(),
    }

    async def execute(self, ctx) -> bool:
        return await run_plan(self.TASKS, self.TASK_DEPENDENCIES, ctx)
