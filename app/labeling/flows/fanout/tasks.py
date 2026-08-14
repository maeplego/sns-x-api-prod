import structlog
from sqlalchemy import select

from app.core import database
from app.core.models import Follow, Post, PostStatus
from app.core.social_models import UserFeedEntry
from app.labeling.context import TaskContext
from app.labeling.plan import Task

logger = structlog.get_logger(__name__)


class FanOutTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None:
                raise ValueError("post not found")
            if post.status != PostStatus.PUBLISHED:
                raise ValueError("post not published yet")
            if post.deleted_at is not None:
                return

            result = await db.execute(
                select(Follow.follower_id).where(Follow.followee_id == post.author_id)
            )
            recipient_ids = {row[0] for row in result.all()}
            recipient_ids.add(post.author_id)

            for user_id in recipient_ids:
                existing = await db.get(UserFeedEntry, (user_id, post.id))
                if existing is not None:
                    continue
                db.add(
                    UserFeedEntry(
                        user_id=user_id,
                        post_id=post.id,
                        author_id=post.author_id,
                        created_at=post.created_at,
                    )
                )
            await db.commit()
            logger.info(
                "fanout_complete",
                post_id=str(post.id),
                recipient_count=len(recipient_ids),
            )
