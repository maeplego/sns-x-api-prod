import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Post, PostEngagement, PostStatus, User
from app.core.social_models import Like
from app.request.schemas import PostCardItem, ReferencedPostItem


def original_id(post: Post) -> uuid.UUID:
    return post.repost_of_id or post.id


async def _referenced_item(
    posts: dict[uuid.UUID, Post],
    authors: dict[uuid.UUID, User],
    post_id: uuid.UUID | None,
) -> ReferencedPostItem | None:
    if post_id is None:
        return None
    post = posts.get(post_id)
    if post is None or post.deleted_at is not None:
        return ReferencedPostItem(
            id=post_id,
            author_id=None,
            author_handle="deleted",
            author_display_name="削除済み",
            body="",
        )
    author = authors.get(post.author_id)
    return ReferencedPostItem(
        id=post.id,
        author_id=post.author_id,
        author_handle=author.handle if author is not None else "unknown",
        author_display_name=author.display_name if author is not None else "Unknown",
        body=post.body,
    )


async def build_post_cards(
    db: AsyncSession,
    posts: list[Post],
    viewer_id: uuid.UUID | None,
) -> list[PostCardItem]:
    if not posts:
        return []

    author_ids = {post.author_id for post in posts}
    ref_ids = {post.quote_of_id for post in posts if post.quote_of_id} | {
        post.repost_of_id for post in posts if post.repost_of_id
    }
    parent_ids = {post.parent_id for post in posts if post.parent_id}
    referenced: dict[uuid.UUID, Post] = {}
    if ref_ids:
        ref_rows = await db.execute(select(Post).where(Post.id.in_(ref_ids)))
        referenced = {post.id: post for post in ref_rows.scalars().all()}
        author_ids |= {post.author_id for post in referenced.values()}

    parents: dict[uuid.UUID, Post] = {}
    if parent_ids:
        parent_rows = await db.execute(select(Post).where(Post.id.in_(parent_ids)))
        parents = {post.id: post for post in parent_rows.scalars().all()}
        author_ids |= {post.author_id for post in parents.values()}

    authors_result = await db.execute(select(User).where(User.id.in_(author_ids)))
    authors = {user.id: user for user in authors_result.scalars().all()}

    engagement_ids = {post.id for post in posts} | {
        post.repost_of_id for post in posts if post.repost_of_id
    }
    engagements: dict[uuid.UUID, PostEngagement] = {}
    if engagement_ids:
        rows = await db.execute(select(PostEngagement).where(PostEngagement.post_id.in_(engagement_ids)))
        engagements = {row.post_id: row for row in rows.scalars().all()}

    liked_ids: set[uuid.UUID] = set()
    reposted_ids: set[uuid.UUID] = set()
    if viewer_id is not None:
        like_targets = {original_id(post) for post in posts}
        like_rows = await db.execute(
            select(Like.post_id).where(Like.user_id == viewer_id, Like.post_id.in_(like_targets))
        )
        liked_ids = {row[0] for row in like_rows.all()}
        repost_rows = await db.execute(
            select(Post.repost_of_id).where(
                Post.author_id == viewer_id,
                Post.repost_of_id.in_(like_targets),
                Post.deleted_at.is_(None),
                Post.status == PostStatus.PUBLISHED,
            )
        )
        reposted_ids = {row[0] for row in repost_rows.all() if row[0] is not None}

    cards: list[PostCardItem] = []
    for post in posts:
        author = authors.get(post.author_id)
        target_id = original_id(post)
        engagement = engagements.get(target_id)
        parent_handle = None
        if post.parent_id is not None:
            parent = parents.get(post.parent_id)
            if parent is not None:
                parent_author = authors.get(parent.author_id)
                if parent_author is not None:
                    parent_handle = parent_author.handle
        cards.append(
            PostCardItem(
                id=post.id,
                author_id=post.author_id,
                author_handle=author.handle if author is not None else "unknown",
                author_display_name=author.display_name if author is not None else "Unknown",
                body=post.body,
                created_at=post.created_at,
                parent_id=post.parent_id,
                parent_author_handle=parent_handle,
                like_count=engagement.like_count if engagement is not None else 0,
                reply_count=engagement.reply_count if engagement is not None else 0,
                repost_count=engagement.repost_count if engagement is not None else 0,
                liked=target_id in liked_ids,
                reposted=target_id in reposted_ids,
                quote_of=await _referenced_item(referenced, authors, post.quote_of_id),
                repost_of=await _referenced_item(referenced, authors, post.repost_of_id),
            )
        )
    return cards
