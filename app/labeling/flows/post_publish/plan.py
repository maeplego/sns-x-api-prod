from app.core.registry import register
from app.labeling.events import POST_CREATED
from app.labeling.flows.post_publish.tasks import PublishPostTask, ValidatePostTask
from app.labeling.plan import run_plan
from app.labeling.registry import Plan


@register
class PostPublishPlan(Plan):
    KEY = "post_publish"
    EVENT_TYPES = [POST_CREATED]
    ORDER = 0

    TASKS = {
        "validate": ValidatePostTask,
        "publish": PublishPostTask,
    }

    TASK_DEPENDENCIES = {
        "validate": set(),
        "publish": {"validate"},
    }

    async def execute(self, ctx) -> bool:
        return await run_plan(self.TASKS, self.TASK_DEPENDENCIES, ctx)
