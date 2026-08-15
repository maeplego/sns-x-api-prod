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
            if not post.body.strip() and post.repost_of_id is None:
                raise ValueError("post body empty")
            if post.parent_id is not None:
                parent = await db.get(Post, post.parent_id)
                if (
                    parent is None
                    or parent.deleted_at is not None
                    or parent.status != PostStatus.PUBLISHED
                ):
                    raise ValueError("parent post not available")
            target_id = post.quote_of_id or post.repost_of_id
            if target_id is not None:
                target = await db.get(Post, target_id)
                if (
                    target is None
                    or target.deleted_at is not None
                    or target.status != PostStatus.PUBLISHED
                ):
                    raise ValueError("referenced post not available")


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
            if post.status != PostStatus.PROCESSING:
                logger.warning(
                    "post_already_published_not_failed",
                    post_id=str(post.id),
                    status=post.status.value,
                    errors=ctx.errors,
                )
                return
            post.status = PostStatus.FAILED
            await db.commit()
            logger.warning("post_failed", post_id=str(post.id), errors=ctx.errors)
