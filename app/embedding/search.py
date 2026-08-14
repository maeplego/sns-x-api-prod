import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.embedding_models import PostEmbedding
from app.core.models import Post, PostStatus, PostVisibility
from app.embedding.encoder import cosine_similarity
from app.request.feed.types import FeedQuery


async def search_similar_posts(
    db: AsyncSession,
    query: FeedQuery,
    *,
    limit: int,
) -> list[tuple[Post, float]]:
    viewer_vector = query.viewer_interest_vector
    if viewer_vector is None:
        return []

    exclude_authors = query.following_ids | query.blocked_user_ids | {query.viewer_id}

    if settings.app_env == "test":
        return await _search_python(db, query, viewer_vector, exclude_authors, limit)
    return await _search_postgres(db, query, viewer_vector, exclude_authors, limit)


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
        )
        .order_by(distance)
        .limit(limit)
    )
    if exclude_authors:
        stmt = stmt.where(Post.author_id.not_in(exclude_authors))

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
        )
    )
    if exclude_authors:
        stmt = stmt.where(Post.author_id.not_in(exclude_authors))

    result = await db.execute(stmt)
    scored: list[tuple[Post, float]] = []
    for post, embedding in result.all():
        scored.append((post, cosine_similarity(viewer_vector, embedding)))
    scored.sort(key=lambda row: row[1], reverse=True)
    return scored[:limit]
