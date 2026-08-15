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
                        repost_count=0,
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


class IncrementRepostCountTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None or post.repost_of_id is None:
                return
            if post.status != PostStatus.PUBLISHED or post.deleted_at is not None:
                return

            original_id = post.repost_of_id
            count = await db.scalar(
                select(func.count())
                .select_from(Post)
                .where(
                    Post.repost_of_id == original_id,
                    Post.status == PostStatus.PUBLISHED,
                    Post.deleted_at.is_(None),
                )
            )
            engagement = await db.get(PostEngagement, original_id)
            if engagement is None:
                db.add(
                    PostEngagement(
                        post_id=original_id,
                        like_count=0,
                        reply_count=0,
                        repost_count=int(count or 0),
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
                engagement.repost_count = int(count or 0)
                engagement.updated_at = datetime.now(UTC)
            await db.commit()
            logger.info(
                "repost_count_updated",
                original_id=str(original_id),
                repost_count=int(count or 0),
            )


class NotifyRepostTask(Task):
    @classmethod
    async def exec(cls, ctx: TaskContext) -> None:
        async with database.SessionLocal() as db:
            post = await db.get(Post, ctx.post_id)
            if post is None or post.repost_of_id is None:
                return
            if post.status != PostStatus.PUBLISHED or post.deleted_at is not None:
                return

            original = await db.get(Post, post.repost_of_id)
            if original is None or original.author_id == post.author_id:
                return

            existing = await db.execute(
                select(Notification).where(
                    Notification.user_id == original.author_id,
                    Notification.type == "post_reposted",
                )
            )
            for row in existing.scalars().all():
                if row.payload_json.get("repost_id") == str(post.id):
                    return

            author = await db.get(User, post.author_id)
            db.add(
                Notification(
                    user_id=original.author_id,
                    type="post_reposted",
                    payload_json={
                        "post_id": str(original.id),
                        "repost_id": str(post.id),
                        "reposter_id": str(post.author_id),
                        "reposter_handle": author.handle if author is not None else "",
                    },
                )
            )
            await db.commit()
            logger.info("repost_notified", original_id=str(original.id), repost_id=str(post.id))
