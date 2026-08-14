import asyncio
import logging
from abc import ABC, abstractmethod

from app.labeling.context import TaskContext

logger = logging.getLogger(__name__)


class TaskStopExecution(Exception):
    pass


class Task(ABC):
    @classmethod
    @abstractmethod
    async def exec(cls, ctx: TaskContext) -> None: ...


async def run_plan(
    tasks: dict[str, type[Task]],
    dependencies: dict[str, set[str]],
    ctx: TaskContext,
) -> bool:
    completed: set[str] = set()
    failed = False

    while len(completed) < len(tasks):
        ready = [
            name
            for name in tasks
            if name not in completed and dependencies.get(name, set()).issubset(completed)
        ]
        if not ready:
            ctx.errors.append("deadlock or missing task dependency")
            return False

        results = await asyncio.gather(
            *(tasks[name].exec(ctx) for name in ready),
            return_exceptions=True,
        )
        for name, result in zip(ready, results, strict=True):
            completed.add(name)
            if isinstance(result, Exception):
                logger.exception("task_failed task=%s", name, exc_info=result)
                ctx.errors.append(f"{name}: {result}")
                failed = True

        if failed:
            return False

    return True
