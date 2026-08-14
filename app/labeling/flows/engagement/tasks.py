from datetime import UTC, datetime

import structlog

from app.core import database
from app.core.models import Post, PostEngagement, PostStatus
from app.labeling.context import TaskContext
from app.labeling.plan import Task

logger = structlog.get_logger(__name__)


class EngagementInitTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None:
                raise ValueError("post not found")
            if post.status != PostStatus.PUBLISHED:
                raise ValueError("post not published yet")

            existing = await db.get(PostEngagement, ctx.post_id)
            if existing is not None:
                return

            db.add(
                PostEngagement(
                    post_id=ctx.post_id,
                    like_count=0,
                    reply_count=0,
                    updated_at=datetime.now(UTC),
                )
            )
            await db.commit()
            logger.info("engagement_initialized", post_id=str(ctx.post_id))
