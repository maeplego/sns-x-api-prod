import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Block, Follow, Mute, Post, PostEngagement, PostStatus, PostVisibility, User
from app.core.queue import get_event_bus
from app.core.social_models import MutedKeyword
from app.labeling.events import POST_CREATED
from app.policy.engine import PolicyContext, PolicyVerdict, evaluate_rules
from app.policy.rules import thread_policy
from app.request.auth import get_current_user, get_optional_user
from app.request.feed.types import FeedCandidate
from app.request.post_cards import build_post_cards
from app.request.rate_limit import rate_limit
from app.request.schemas import (
    PostAcceptedResponse,
    PostCardItem,
    PostCreateRequest,
    PostResponse,
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


async def _load_reference(db: AsyncSession, post_id: uuid.UUID) -> Post:
    post = await db.get(Post, post_id)
    if post is None or post.deleted_at is not None or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.repost_of_id is not None:
        original = await db.get(Post, post.repost_of_id)
        if original is None or original.deleted_at is not None or original.status != PostStatus.PUBLISHED:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        return original
    return post


async def _assert_can_view_reference(db: AsyncSession, viewer: User, target: Post) -> None:
    if target.author_id == viewer.id:
        return
    follows = await db.scalar(
        select(Follow).where(
            Follow.follower_id == viewer.id,
            Follow.followee_id == target.author_id,
        )
    )
    author = await db.get(User, target.author_id)
    if author is not None and author.is_private and follows is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot reference this post")
    if target.visibility == PostVisibility.FOLLOWERS_ONLY and follows is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot reference this post")


@router.post(
    "",
    response_model=PostAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("post", limit=30, per_user=True))],
)
async def create_post(
    body: PostCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostAcceptedResponse:
    visibility = body.visibility
    parent_id = body.parent_id
    quote_of_id = body.quote_of_id
    repost_of_id = body.repost_of_id
    root_id = None
    if parent_id is not None:
        parent = await _load_parent_or_404(db, parent_id)
        await _assert_can_reply(db, current_user, parent)
        visibility = parent.visibility
        root_id = parent.root_id or parent.id
    if quote_of_id is not None:
        quoted = await _load_reference(db, quote_of_id)
        await _assert_can_view_reference(db, current_user, quoted)
        quote_of_id = quoted.id
    if repost_of_id is not None:
        original = await _load_reference(db, repost_of_id)
        await _assert_can_view_reference(db, current_user, original)
        existing = await db.scalar(
            select(Post).where(
                Post.author_id == current_user.id,
                Post.repost_of_id == original.id,
                Post.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already reposted")
        repost_of_id = original.id

    post = Post(
        author_id=current_user.id,
        body=body.body,
        visibility=visibility,
        status=PostStatus.PROCESSING,
        parent_id=parent_id,
        root_id=root_id,
        quote_of_id=quote_of_id,
        repost_of_id=repost_of_id,
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

    from app.core.safety_models import SafetyTargetType
    from app.safety.labels import labels_for_targets

    post_labels = await labels_for_targets(
        db, target_type=SafetyTargetType.POST, target_ids={row.id for row in posts}
    )
    author_labels = await labels_for_targets(
        db, target_type=SafetyTargetType.USER, target_ids=set(author_ids)
    )

    visible_posts: list[Post] = []
    interstitial_ids: set[uuid.UUID] = set()
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
            safety_labels=set(post_labels.get(row.id, set())),
            author_safety_labels=set(author_labels.get(row.author_id, set())),
            source="in_network",
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
            viewer_birthdate=current_user.birthdate,
        )
        verdict, _ = evaluate_rules(rules, context)
        if verdict == PolicyVerdict.DROP:
            continue
        if verdict == PolicyVerdict.INTERSTITIAL:
            interstitial_ids.add(row.id)
        visible_posts.append(row)

    visible_ids = {item.id for item in visible_posts if item.parent_id is None}
    changed = True
    while changed:
        changed = False
        for item in visible_posts:
            if item.id not in visible_ids and item.parent_id in visible_ids:
                visible_ids.add(item.id)
                changed = True
    visible_posts = [item for item in visible_posts if item.id in visible_ids]
    visible_posts.sort(key=lambda item: (item.parent_id is not None, item.created_at, str(item.id)))
    items = await build_post_cards(db, visible_posts, current_user.id)
    for card in items:
        if card.id in interstitial_ids:
            card.body = ""
            card.visibility_state = "interstitial"
            card.interstitial_reason = "sensitive"
            card.quote_of = None
            card.repost_of = None

    return ThreadResponse(root_id=root_id, items=items)


@router.get("/{post_id}/reveal", response_model=PostCardItem)
async def reveal_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostCardItem:
    """Return full body for an interstitial-eligible NSFW post (adults only)."""
    from app.core.age import is_adult
    from app.core.safety_models import SafetyTargetType
    from app.safety.labels import labels_for_targets

    if not is_adult(current_user.birthdate):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Age restricted")

    post = await db.get(Post, post_id)
    if post is None or post.deleted_at is not None or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    labels = await labels_for_targets(
        db, target_type=SafetyTargetType.POST, target_ids={post.id}
    )
    post_labels = set(labels.get(post.id, set()))
    if "nsfw" not in post_labels:
        # Still allow reveal of plain posts (idempotent UX)
        pass

    cards = await build_post_cards(db, [post], current_user.id)
    if not cards:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    card = cards[0]
    card.visibility_state = "allow"
    card.interstitial_reason = None
    card.safety_labels = sorted(post_labels)
    return card


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
    if post.repost_of_id is not None:
        engagement = await db.get(PostEngagement, post.repost_of_id)
        if engagement is not None and engagement.repost_count > 0:
            engagement.repost_count -= 1
            engagement.updated_at = datetime.now(UTC)
    await db.commit()


@router.post("/{post_id}/repost", response_model=PostAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def repost_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostAcceptedResponse:
    return await create_post(
        PostCreateRequest(repost_of_id=post_id),
        current_user,
        db,
    )


@router.delete("/{post_id}/repost", status_code=status.HTTP_204_NO_CONTENT)
async def unrepost_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    original = await _load_reference(db, post_id)
    existing = await db.scalar(
        select(Post).where(
            Post.author_id == current_user.id,
            Post.repost_of_id == original.id,
            Post.deleted_at.is_(None),
        )
    )
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not reposted")
    await delete_post(existing.id, current_user, db)
