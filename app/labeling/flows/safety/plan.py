from app.core.registry import register
from app.labeling.events import POST_CREATED
from app.labeling.flows.safety.tasks import ApplyPostSafetyLabelsTask
from app.labeling.plan import run_plan
from app.labeling.registry import Plan


@register
class PostSafetyLabelPlan(Plan):
    KEY = "post_safety_labels"
    EVENT_TYPES = [POST_CREATED]
    ORDER = 15

    TASKS = {
        "apply_labels": ApplyPostSafetyLabelsTask,
    }

    TASK_DEPENDENCIES = {
        "apply_labels": set(),
    }

    async def execute(self, ctx) -> bool:
        return await run_plan(self.TASKS, self.TASK_DEPENDENCIES, ctx)
