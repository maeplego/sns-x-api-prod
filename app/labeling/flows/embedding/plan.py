from app.core.registry import register
from app.labeling.events import POST_CREATED
from app.labeling.flows.embedding.tasks import GenerateEmbeddingTask
from app.labeling.plan import run_plan
from app.labeling.registry import Plan


@register
class EmbeddingPlan(Plan):
    KEY = "embedding"
    EVENT_TYPES = [POST_CREATED]
    ORDER = 25

    TASKS = {
        "embed": GenerateEmbeddingTask,
    }

    TASK_DEPENDENCIES = {
        "embed": set(),
    }

    async def execute(self, ctx) -> bool:
        return await run_plan(self.TASKS, self.TASK_DEPENDENCIES, ctx)
