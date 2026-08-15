import uuid

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Block, Follow, Mute, Post, PostStatus, PostVisibility, User
from app.core.social_models import Like
from app.request.auth import get_current_user, get_optional_user
from app.request.feed.types import decode_cursor, encode_cursor
from app.request.post_cards import build_post_cards
from app.request.schemas import (
    PostListResponse,
    ProfileUpdateRequest,
    UserListItem,
    UserListResponse,
    UserPublicResponse,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["users"])


async def _get_user_by_handle(db: AsyncSession, handle: str) -> User:
    user = await db.scalar(select(User).where(User.handle == handle.lower()))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _counts(db: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    follower_count = await db.scalar(
        select(func.count()).select_from(Follow).where(Follow.followee_id == user_id)
    )
    following_count = await db.scalar(
        select(func.count()).select_from(Follow).where(Follow.follower_id == user_id)
    )
    return int(follower_count or 0), int(following_count or 0)


async def _is_following(db: AsyncSession, follower_id: uuid.UUID, followee_id: uuid.UUID) -> bool:
    row = await db.scalar(
        select(Follow).where(
            Follow.follower_id == follower_id,
            Follow.followee_id == followee_id,
        )
    )
    return row is not None


def _parse_cursor(cursor: str | None) -> tuple | None:
    if cursor is None:
        return None
    try:
        return decode_cursor(cursor)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor",
        ) from exc


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.bio is not None:
        current_user.bio = body.bio
    if body.is_private is not None:
        current_user.is_private = body.is_private
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/{handle}", response_model=UserPublicResponse)
async def get_user_by_handle(
    handle: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> UserPublicResponse:
    user = await _get_user_by_handle(db, handle)
    follower_count, following_count = await _counts(db, user.id)
    is_self = current_user is not None and current_user.id == user.id
    following = False
    blocking = False
    muting = False
    if current_user is not None and not is_self:
        following = await _is_following(db, current_user.id, user.id)
        blocking = (
            await db.scalar(
                select(Block).where(
                    Block.blocker_id == current_user.id,
                    Block.blocked_id == user.id,
                )
            )
            is not None
        )
        muting = (
            await db.scalar(
                select(Mute).where(
                    Mute.muter_id == current_user.id,
                    Mute.muted_id == user.id,
                )
            )
            is not None
        )
    return UserPublicResponse(
        id=user.id,
        handle=user.handle,
        display_name=user.display_name,
        bio=user.bio,
        is_private=user.is_private,
        status=user.status,
        created_at=user.created_at,
        follower_count=follower_count,
        following_count=following_count,
        is_following=following,
        is_self=is_self,
        is_blocking=blocking,
        is_muting=muting,
    )


@router.get("/{handle}/posts", response_model=PostListResponse)
async def get_user_posts(
    handle: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    tab: Literal["posts", "replies"] = Query(default="posts"),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> PostListResponse:
    user = await _get_user_by_handle(db, handle)
    viewer_follows = False
    is_self = current_user is not None and current_user.id == user.id
    if current_user is not None and not is_self:
        viewer_follows = await _is_following(db, current_user.id, user.id)

    if user.is_private and not is_self and not viewer_follows:
        return PostListResponse(items=[], next_cursor=None)

    stmt = (
        select(Post)
        .where(
            Post.author_id == user.id,
            Post.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
        )
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(limit + 1)
    )
    if tab == "replies":
        stmt = stmt.where(Post.parent_id.is_not(None))
    else:
        stmt = stmt.where(Post.parent_id.is_(None))
    if not is_self and not viewer_follows:
        stmt = stmt.where(Post.visibility == PostVisibility.PUBLIC)

    parsed = _parse_cursor(cursor)
    if parsed is not None:
        cursor_time, cursor_id = parsed
        stmt = stmt.where(
            or_(
                Post.created_at < cursor_time,
                and_(Post.created_at == cursor_time, Post.id < cursor_id),
            )
        )

    posts = list((await db.execute(stmt)).scalars().all())
    has_more = len(posts) > limit
    page = posts[:limit]
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return PostListResponse(
        items=await build_post_cards(db, page, current_user.id if current_user else None),
        next_cursor=next_cursor,
    )


@router.get("/{handle}/likes", response_model=PostListResponse)
async def get_user_likes(
    handle: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostListResponse:
    user = await _get_user_by_handle(db, handle)
    if current_user.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Likes are private")

    stmt = (
        select(Post, Like.created_at)
        .join(Like, Like.post_id == Post.id)
        .where(
            Like.user_id == user.id,
            Post.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
        )
        .order_by(Like.created_at.desc(), Post.id.desc())
        .limit(limit + 1)
    )
    parsed = _parse_cursor(cursor)
    if parsed is not None:
        cursor_time, cursor_id = parsed
        stmt = stmt.where(
            or_(
                Like.created_at < cursor_time,
                and_(Like.created_at == cursor_time, Post.id < cursor_id),
            )
        )

    rows = list((await db.execute(stmt)).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = None
    if has_more and page:
        last_post, last_liked_at = page[-1]
        next_cursor = encode_cursor(last_liked_at, last_post.id)

    return PostListResponse(
        items=await build_post_cards(db, [row[0] for row in page], current_user.id),
        next_cursor=next_cursor,
    )


@router.get("/{handle}/followers", response_model=UserListResponse)
async def get_followers(
    handle: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> UserListResponse:
    user = await _get_user_by_handle(db, handle)
    rows = await db.execute(
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.followee_id == user.id)
        .order_by(Follow.created_at.desc())
        .limit(limit)
    )
    users = list(rows.scalars().all())
    viewer_id = current_user.id if current_user is not None else None
    following_ids: set[uuid.UUID] = set()
    if viewer_id is not None:
        followed = await db.execute(
            select(Follow.followee_id).where(Follow.follower_id == viewer_id)
        )
        following_ids = {row[0] for row in followed.all()}
    return UserListResponse(
        items=[
            UserListItem(
                id=item.id,
                handle=item.handle,
                display_name=item.display_name,
                bio=item.bio,
                is_following=item.id in following_ids,
            )
            for item in users
        ]
    )


@router.get("/{handle}/following", response_model=UserListResponse)
async def get_following(
    handle: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> UserListResponse:
    user = await _get_user_by_handle(db, handle)
    rows = await db.execute(
        select(User)
        .join(Follow, Follow.followee_id == User.id)
        .where(Follow.follower_id == user.id)
        .order_by(Follow.created_at.desc())
        .limit(limit)
    )
    users = list(rows.scalars().all())
    viewer_id = current_user.id if current_user is not None else None
    following_ids: set[uuid.UUID] = set()
    if viewer_id is not None:
        followed = await db.execute(
            select(Follow.followee_id).where(Follow.follower_id == viewer_id)
        )
        following_ids = {row[0] for row in followed.all()}
    return UserListResponse(
        items=[
            UserListItem(
                id=item.id,
                handle=item.handle,
                display_name=item.display_name,
                bio=item.bio,
                is_following=item.id in following_ids,
            )
            for item in users
        ]
    )
