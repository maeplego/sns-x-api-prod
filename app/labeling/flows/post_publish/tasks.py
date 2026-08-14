import structlog

from app.core import database
from app.core.models import Post, PostStatus
from app.labeling.context import TaskContext
from app.labeling.plan import Task

logger = structlog.get_logger(__name__)


class ValidatePostTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None:
                raise ValueError("post not found")
            if not post.body.strip():
                raise ValueError("post body empty")


class PublishPostTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None:
                raise ValueError("post not found")
            post.status = PostStatus.PUBLISHED
            await db.commit()
            logger.info("post_published", post_id=str(post.id), author_id=str(post.author_id))


class MarkFailedPostTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None:
                return
            post.status = PostStatus.FAILED
            await db.commit()
            logger.warning("post_failed", post_id=str(post.id), errors=ctx.errors)
