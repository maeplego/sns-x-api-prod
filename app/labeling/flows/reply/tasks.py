from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select

from app.core import database
from app.core.models import Post, PostEngagement, PostStatus, User
from app.core.social_models import Notification
from app.labeling.context import TaskContext
from app.labeling.plan import Task

logger = structlog.get_logger(__name__)


class IncrementReplyCountTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None or post.parent_id is None:
                return
            if post.status != PostStatus.PUBLISHED or post.deleted_at is not None:
                return

            reply_count = await db.scalar(
                select(func.count())
                .select_from(Post)
                .where(
                    Post.parent_id == post.parent_id,
                    Post.status == PostStatus.PUBLISHED,
                    Post.deleted_at.is_(None),
                )
            )
            engagement = await db.get(PostEngagement, post.parent_id)
            if engagement is None:
                db.add(
                    PostEngagement(
                        post_id=post.parent_id,
                        like_count=0,
                        reply_count=int(reply_count or 0),
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
                engagement.reply_count = int(reply_count or 0)
                engagement.updated_at = datetime.now(UTC)
            await db.commit()
            logger.info(
                "reply_count_updated",
                parent_id=str(post.parent_id),
                reply_count=int(reply_count or 0),
            )


class NotifyReplyTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None or post.parent_id is None:
                return
            if post.status != PostStatus.PUBLISHED or post.deleted_at is not None:
                return

            parent = await db.get(Post, post.parent_id)
            if parent is None or parent.author_id == post.author_id:
                return

            existing = await db.execute(
                select(Notification).where(
                    Notification.user_id == parent.author_id,
                    Notification.type == "post_replied",
                )
            )
            for row in existing.scalars().all():
                if row.payload_json.get("reply_id") == str(post.id):
                    return

            author = await db.get(User, post.author_id)
            db.add(
                Notification(
                    user_id=parent.author_id,
                    type="post_replied",
                    payload_json={
                        "post_id": str(parent.id),
                        "reply_id": str(post.id),
                        "replier_id": str(post.author_id),
                        "replier_handle": author.handle if author is not None else "",
                    },
                )
            )
            await db.commit()
            logger.info("reply_notified", parent_id=str(parent.id), reply_id=str(post.id))
