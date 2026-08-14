import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Block, Follow, Mute, Post, PostStatus, PostVisibility, User
from app.core.queue import get_event_bus
from app.core.social_models import MutedKeyword
from app.labeling.events import POST_CREATED
from app.policy.engine import PolicyContext, PolicyVerdict, evaluate_rules
from app.policy.rules import thread_policy
from app.request.auth import get_current_user, get_optional_user
from app.request.feed.types import FeedCandidate
from app.request.schemas import (
    PostAcceptedResponse,
    PostCreateRequest,
    PostResponse,
    ThreadPostItem,
    ThreadResponse,
)

router = APIRouter(prefix="/posts", tags=["posts"])


async def _load_parent_or_404(db: AsyncSession, parent_id: uuid.UUID) -> Post:
    parent = await db.get(Post, parent_id)
    if parent is None or parent.deleted_at is not None or parent.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent post not found")
    return parent


async def _assert_can_reply(
    db: AsyncSession, viewer: User, parent: Post
) -> None:
    if parent.author_id == viewer.id:
        return

    blocked = await db.scalar(
        select(Block).where(
            or_(
                and_(Block.blocker_id == viewer.id, Block.blocked_id == parent.author_id),
                and_(Block.blocker_id == parent.author_id, Block.blocked_id == viewer.id),
            )
        )
    )
    if blocked is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot reply")

    follows = await db.scalar(
        select(Follow).where(
            Follow.follower_id == viewer.id,
            Follow.followee_id == parent.author_id,
        )
    )
    author = await db.get(User, parent.author_id)
    if author is not None and author.is_private and follows is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot reply")
    if parent.visibility == PostVisibility.FOLLOWERS_ONLY and follows is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot reply")


@router.post("", response_model=PostAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_post(
    body: PostCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostAcceptedResponse:
    visibility = body.visibility
    parent_id = body.parent_id
    root_id = None
    if parent_id is not None:
        parent = await _load_parent_or_404(db, parent_id)
        await _assert_can_reply(db, current_user, parent)
        visibility = parent.visibility
        root_id = parent.root_id or parent.id

    post = Post(
        author_id=current_user.id,
        body=body.body,
        visibility=visibility,
        status=PostStatus.PROCESSING,
        parent_id=parent_id,
        root_id=root_id,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    await get_event_bus().publish(
        POST_CREATED,
        {"post_id": str(post.id), "author_id": str(current_user.id)},
    )

    return PostAcceptedResponse(
        id=post.id,
        author_id=post.author_id,
        status=post.status,
    )


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> Post:
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.deleted_at.is_(None))
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if post.status != PostStatus.PUBLISHED:
        if current_user is None or current_user.id != post.author_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    return post


@router.get("/{post_id}/thread", response_model=ThreadResponse)
async def get_thread(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.deleted_at.is_(None))
    )
    post = result.scalar_one_or_none()
    if post is None or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    root_id = post.root_id or post.id
    thread_result = await db.execute(
        select(Post)
        .where(
            Post.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
            or_(Post.id == root_id, Post.root_id == root_id),
        )
        .order_by(Post.created_at.asc(), Post.id.asc())
    )
    posts = list(thread_result.scalars().all())
    if not posts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    author_ids = {row.author_id for row in posts}
    authors_result = await db.execute(select(User).where(User.id.in_(author_ids)))
    authors = {user.id: user for user in authors_result.scalars().all()}

    following_ids = {
        row[0]
        for row in (
            await db.execute(select(Follow.followee_id).where(Follow.follower_id == current_user.id))
        ).all()
    }
    following_ids.add(current_user.id)
    blocked_ids = {
        row[0]
        for row in (
            await db.execute(select(Block.blocked_id).where(Block.blocker_id == current_user.id))
        ).all()
    }
    muted_ids = {
        row[0]
        for row in (
            await db.execute(select(Mute.muted_id).where(Mute.muter_id == current_user.id))
        ).all()
    }
    muted_keywords = {
        row[0]
        for row in (
            await db.execute(
                select(MutedKeyword.keyword).where(MutedKeyword.user_id == current_user.id)
            )
        ).all()
    }

    items: list[ThreadPostItem] = []
    rules = thread_policy()
    for row in posts:
        author = authors.get(row.author_id)
        candidate = FeedCandidate(
            id=row.id,
            author_id=row.author_id,
            body=row.body,
            created_at=row.created_at,
            visibility=row.visibility,
            parent_id=row.parent_id,
            root_id=row.root_id,
        )
        if author is not None:
            candidate.author_handle = author.handle
            candidate.author_display_name = author.display_name
            candidate.author_is_private = author.is_private
            candidate.author_status = author.status
        context = PolicyContext(
            viewer_id=current_user.id,
            following_ids=following_ids,
            blocked_user_ids=blocked_ids,
            muted_user_ids=muted_ids,
            muted_keywords=muted_keywords,
            candidate=candidate,
        )
        verdict, _ = evaluate_rules(rules, context)
        if verdict == PolicyVerdict.DROP:
            continue
        items.append(
            ThreadPostItem(
                id=row.id,
                author_id=row.author_id,
                author_handle=candidate.author_handle or "unknown",
                author_display_name=candidate.author_display_name or "Unknown",
                body=row.body,
                parent_id=row.parent_id,
                created_at=row.created_at,
            )
        )

    visible_ids = {item.id for item in items if item.parent_id is None}
    changed = True
    while changed:
        changed = False
        for item in items:
            if item.id not in visible_ids and item.parent_id in visible_ids:
                visible_ids.add(item.id)
                changed = True
    items = [item for item in items if item.id in visible_ids]
    items.sort(key=lambda item: (item.parent_id is not None, item.created_at, str(item.id)))

    return ThreadResponse(root_id=root_id, items=items)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.deleted_at.is_(None))
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your post")

    post.deleted_at = datetime.now(UTC)
    await db.commit()
