import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.embedding_models import PostEmbedding
from app.core.models import Post, PostStatus, PostVisibility
from app.core.safety_models import SafetyLabel, SafetyTargetType
from app.embedding.encoder import cosine_similarity
from app.request.feed.types import FeedQuery
from app.safety.labels import OON_DROP_LABELS

MIN_SIMILARITY = 0.12
MAX_PER_AUTHOR = 2


async def search_similar_posts(
    db: AsyncSession,
    query: FeedQuery,
    *,
    limit: int,
) -> list[tuple[Post, float]]:
    viewer_vector = query.viewer_interest_vector
    if viewer_vector is None:
        return []

    exclude_authors = (
        query.following_ids
        | query.blocked_user_ids
        | query.muted_user_ids
        | query.not_interested_author_ids
        | {query.viewer_id}
    )
    # Over-fetch then filter labels / diversify authors.
    fetch_limit = max(limit * 4, 40)

    if settings.app_env == "test":
        rows = await _search_python(db, query, viewer_vector, exclude_authors, fetch_limit)
    else:
        rows = await _search_postgres(db, query, viewer_vector, exclude_authors, fetch_limit)

    return await _post_filter(db, rows, limit)


async def _blocked_post_ids(db: AsyncSession, post_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not post_ids:
        return set()
    rows = await db.execute(
        select(SafetyLabel.target_id).where(
            SafetyLabel.target_type == SafetyTargetType.POST,
            SafetyLabel.target_id.in_(post_ids),
            SafetyLabel.label.in_(OON_DROP_LABELS),
        )
    )
    return {row[0] for row in rows.all()}


async def _blocked_author_ids(db: AsyncSession, author_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not author_ids:
        return set()
    rows = await db.execute(
        select(SafetyLabel.target_id).where(
            SafetyLabel.target_type == SafetyTargetType.USER,
            SafetyLabel.target_id.in_(author_ids),
            SafetyLabel.label.in_(OON_DROP_LABELS),
        )
    )
    return {row[0] for row in rows.all()}


async def _post_filter(
    db: AsyncSession,
    rows: list[tuple[Post, float]],
    limit: int,
) -> list[tuple[Post, float]]:
    if not rows:
        return []
    labeled_posts = await _blocked_post_ids(db, [post.id for post, _ in rows])
    labeled_authors = await _blocked_author_ids(db, {post.author_id for post, _ in rows})
    per_author: dict[uuid.UUID, int] = {}
    kept: list[tuple[Post, float]] = []
    for post, similarity in rows:
        if similarity < MIN_SIMILARITY:
            continue
        if post.id in labeled_posts or post.author_id in labeled_authors:
            continue
        count = per_author.get(post.author_id, 0)
        if count >= MAX_PER_AUTHOR:
            continue
        per_author[post.author_id] = count + 1
        kept.append((post, similarity))
        if len(kept) >= limit:
            break
    return kept


async def _search_postgres(
    db: AsyncSession,
    query: FeedQuery,
    viewer_vector: list[float],
    exclude_authors: set[uuid.UUID],
    limit: int,
) -> list[tuple[Post, float]]:
    distance = PostEmbedding.embedding.cosine_distance(viewer_vector)
    stmt = (
        select(Post, (1 - distance).label("similarity"))
        .join(PostEmbedding, PostEmbedding.post_id == Post.id)
        .where(
            Post.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
            Post.visibility == PostVisibility.PUBLIC,
            Post.parent_id.is_(None),
            Post.repost_of_id.is_(None),
        )
        .order_by(distance)
        .limit(limit)
    )
    if exclude_authors:
        stmt = stmt.where(Post.author_id.not_in(exclude_authors))
    if query.hidden_post_ids:
        stmt = stmt.where(Post.id.not_in(query.hidden_post_ids))

    result = await db.execute(stmt)
    return [(post, float(similarity)) for post, similarity in result.all()]


async def _search_python(
    db: AsyncSession,
    query: FeedQuery,
    viewer_vector: list[float],
    exclude_authors: set[uuid.UUID],
    limit: int,
) -> list[tuple[Post, float]]:
    stmt = (
        select(Post, PostEmbedding.embedding)
        .join(PostEmbedding, PostEmbedding.post_id == Post.id)
        .where(
            Post.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
            Post.visibility == PostVisibility.PUBLIC,
            Post.parent_id.is_(None),
            Post.repost_of_id.is_(None),
        )
    )
    if exclude_authors:
        stmt = stmt.where(Post.author_id.not_in(exclude_authors))
    if query.hidden_post_ids:
        stmt = stmt.where(Post.id.not_in(query.hidden_post_ids))

    result = await db.execute(stmt)
    scored: list[tuple[Post, float]] = []
    for post, embedding in result.all():
        scored.append((post, cosine_similarity(viewer_vector, embedding)))
    scored.sort(key=lambda row: row[1], reverse=True)
    return scored[:limit]
