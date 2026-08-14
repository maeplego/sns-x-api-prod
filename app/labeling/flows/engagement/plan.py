from app.core.registry import register
from app.labeling.events import POST_CREATED
from app.labeling.flows.engagement.tasks import EngagementInitTask
from app.labeling.plan import run_plan
from app.labeling.registry import Plan


@register
class EngagementInitPlan(Plan):
    KEY = "engagement_init"
    EVENT_TYPES = [POST_CREATED]
    ORDER = 100

    TASKS = {
        "init": EngagementInitTask,
    }

    TASK_DEPENDENCIES = {
        "init": set(),
    }

    async def execute(self, ctx) -> bool:
        return await run_plan(self.TASKS, self.TASK_DEPENDENCIES, ctx)
