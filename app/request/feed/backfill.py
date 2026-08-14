import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Post, PostStatus
from app.core.social_models import UserFeedEntry

BACKFILL_LIMIT = 50


async def backfill_followee_posts(
    db: AsyncSession,
    follower_id: uuid.UUID,
    followee_id: uuid.UUID,
    *,
    limit: int = BACKFILL_LIMIT,
) -> int:
    """Copy a followee's recent published posts into the follower's Thunder cache."""
    result = await db.execute(
        select(Post)
        .where(
            Post.author_id == followee_id,
            Post.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
        )
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(limit)
    )
    added = 0
    for post in result.scalars().all():
        existing = await db.get(UserFeedEntry, (follower_id, post.id))
        if existing is not None:
            continue
        db.add(
            UserFeedEntry(
                user_id=follower_id,
                post_id=post.id,
                author_id=post.author_id,
                created_at=post.created_at,
            )
        )
        added += 1
    return added


async def remove_followee_from_feed(
    db: AsyncSession,
    follower_id: uuid.UUID,
    followee_id: uuid.UUID,
) -> None:
    entries = await db.execute(
        select(UserFeedEntry).where(
            UserFeedEntry.user_id == follower_id,
            UserFeedEntry.author_id == followee_id,
        )
    )
    for entry in entries.scalars().all():
        await db.delete(entry)
