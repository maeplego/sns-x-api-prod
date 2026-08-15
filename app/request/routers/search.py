from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Block, Follow, Post, PostEngagement, PostStatus, PostVisibility, User, UserStatus
from app.request.auth import get_current_user
from app.request.post_cards import build_post_cards
from app.request.schemas import SearchResponse, UserListItem

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=100),
    scope: Literal["all", "users", "posts"] = Query(default="all"),
    sort: Literal["latest", "popular"] = Query(default="latest"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    term = f"%{q.strip().lower()}%"
    blocked_rows = await db.execute(
        select(Block.blocked_id).where(Block.blocker_id == current_user.id)
    )
    blocked_ids = {row[0] for row in blocked_rows.all()}
    blocker_rows = await db.execute(
        select(Block.blocker_id).where(Block.blocked_id == current_user.id)
    )
    blocked_ids |= {row[0] for row in blocker_rows.all()}

    users: list[User] = []
    if scope in {"all", "users"}:
        user_stmt = (
            select(User)
            .where(
                User.status == UserStatus.ACTIVE,
                or_(
                    func.lower(User.handle).like(term),
                    func.lower(User.display_name).like(term),
                ),
            )
            .order_by(User.handle.asc())
            .limit(20)
        )
        users = list((await db.execute(user_stmt)).scalars().all())
        if blocked_ids:
            users = [user for user in users if user.id not in blocked_ids]

    following_rows = await db.execute(
        select(Follow.followee_id).where(Follow.follower_id == current_user.id)
    )
    following_ids = {row[0] for row in following_rows.all()}

    posts: list[Post] = []
    if scope in {"all", "posts"}:
        post_stmt = (
            select(Post)
            .join(User, User.id == Post.author_id)
            .where(
                Post.deleted_at.is_(None),
                Post.status == PostStatus.PUBLISHED,
                Post.visibility == PostVisibility.PUBLIC,
                Post.parent_id.is_(None),
                Post.repost_of_id.is_(None),
                User.status == UserStatus.ACTIVE,
                User.is_private.is_(False),
                func.lower(Post.body).like(term),
            )
            .limit(20)
        )
        if blocked_ids:
            post_stmt = post_stmt.where(Post.author_id.not_in(blocked_ids))
        if sort == "popular":
            post_stmt = (
                post_stmt.outerjoin(PostEngagement, PostEngagement.post_id == Post.id)
                .order_by(
                    (
                        func.coalesce(PostEngagement.like_count, 0)
                        + func.coalesce(PostEngagement.reply_count, 0)
                        + func.coalesce(PostEngagement.repost_count, 0)
                    ).desc(),
                    Post.created_at.desc(),
                )
            )
        else:
            post_stmt = post_stmt.order_by(Post.created_at.desc(), Post.id.desc())
        posts = list((await db.execute(post_stmt)).scalars().all())

    return SearchResponse(
        users=[
            UserListItem(
                id=user.id,
                handle=user.handle,
                display_name=user.display_name,
                bio=user.bio,
                is_following=user.id in following_ids,
            )
            for user in users
        ],
        posts=await build_post_cards(db, posts, current_user.id),
    )
