import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Block, Follow, Mute, User, UserStatus
from app.request.feed.schemas import WhoToFollowUserItem

MAX_WHO_TO_FOLLOW_USERS = 3
FOF_FETCH_LIMIT = 20


async def fetch_who_to_follow(
    db: AsyncSession,
    viewer_id: uuid.UUID,
    limit: int = MAX_WHO_TO_FOLLOW_USERS,
) -> list[WhoToFollowUserItem]:
    """Friends-of-friends: people followed by accounts the viewer already follows."""
    following_rows = await db.execute(
        select(Follow.followee_id).where(Follow.follower_id == viewer_id)
    )
    following_ids = {row[0] for row in following_rows.all()}
    if not following_ids:
        return []

    blocked_rows = await db.execute(select(Block.blocked_id).where(Block.blocker_id == viewer_id))
    blocker_rows = await db.execute(select(Block.blocker_id).where(Block.blocked_id == viewer_id))
    muted_rows = await db.execute(select(Mute.muted_id).where(Mute.muter_id == viewer_id))
    excluded = following_ids | {viewer_id}
    excluded |= {row[0] for row in blocked_rows.all()}
    excluded |= {row[0] for row in blocker_rows.all()}
    excluded |= {row[0] for row in muted_rows.all()}

    count_rows = await db.execute(
        select(Follow.followee_id, func.count().label("mutual_count"))
        .where(
            Follow.follower_id.in_(following_ids),
            Follow.followee_id.notin_(excluded),
        )
        .group_by(Follow.followee_id)
        .order_by(func.count().desc(), Follow.followee_id.asc())
        .limit(FOF_FETCH_LIMIT)
    )
    mutual_by_id = {user_id: count for user_id, count in count_rows.all()}
    if not mutual_by_id:
        return []

    users = list(
        (
            await db.execute(
                select(User).where(
                    User.id.in_(mutual_by_id.keys()),
                    User.status == UserStatus.ACTIVE,
                    User.is_private.is_(False),
                )
            )
        ).scalars().all()
    )
    users.sort(key=lambda user: (-mutual_by_id[user.id], user.handle))
    return [
        WhoToFollowUserItem(
            id=user.id,
            handle=user.handle,
            display_name=user.display_name,
            mutual_follow_count=mutual_by_id[user.id],
            reason="mutual_follows",
        )
        for user in users[:limit]
    ]
