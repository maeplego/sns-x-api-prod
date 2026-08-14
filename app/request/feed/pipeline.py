import time
from abc import ABC, abstractmethod

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding_models import PostEmbedding
from app.core.models import Block, Follow, Mute, Post, PostEngagement, PostStatus, User
from app.core.social_models import FeedImpression, MutedKeyword, UserFeedEntry
from app.embedding.encoder import mean_embedding
from app.embedding.search import search_similar_posts
from app.policy.engine import PolicyContext, PolicyVerdict, Rule, evaluate_rules
from app.ranking.scorer import rank_candidates
from app.ranking.weights import RankingWeights, load_weights
from app.request.feed.blender import SourceBlender
from app.request.feed.types import FeedCandidate, FeedQuery, encode_cursor

logger = structlog.get_logger(__name__)


class QueryHydrator(ABC):
    @abstractmethod
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery: ...


class Source(ABC):
    name: str = "source"

    @abstractmethod
    async def fetch(self, db: AsyncSession, query: FeedQuery) -> list[FeedCandidate]: ...


class Hydrator(ABC):
    @abstractmethod
    async def enrich(
        self, db: AsyncSession, query: FeedQuery, candidates: list[FeedCandidate]
    ) -> list[FeedCandidate]: ...


class Selector(ABC):
    @abstractmethod
    def select(
        self, query: FeedQuery, candidates: list[FeedCandidate]
    ) -> tuple[list[FeedCandidate], str | None]: ...


class FollowingQueryHydrator(QueryHydrator):
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery:
        result = await db.execute(
            select(Follow.followee_id).where(Follow.follower_id == query.viewer_id)
        )
        query.following_ids = {row[0] for row in result.all()}
        query.following_ids.add(query.viewer_id)
        return query


class BlockedUserIdsQueryHydrator(QueryHydrator):
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery:
        result = await db.execute(
            select(Block.blocked_id).where(Block.blocker_id == query.viewer_id)
        )
        query.blocked_user_ids = {row[0] for row in result.all()}
        return query


class MutedUserIdsQueryHydrator(QueryHydrator):
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery:
        result = await db.execute(select(Mute.muted_id).where(Mute.muter_id == query.viewer_id))
        query.muted_user_ids = {row[0] for row in result.all()}
        return query


class MutedKeywordsQueryHydrator(QueryHydrator):
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery:
        result = await db.execute(
            select(MutedKeyword.keyword).where(MutedKeyword.user_id == query.viewer_id)
        )
        query.muted_keywords = {row[0] for row in result.all()}
        return query


class SeenPostsQueryHydrator(QueryHydrator):
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery:
        result = await db.execute(
            select(FeedImpression.post_id).where(FeedImpression.viewer_id == query.viewer_id)
        )
        query.seen_post_ids = {row[0] for row in result.all()}
        return query


class ViewerInterestQueryHydrator(QueryHydrator):
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery:
        result = await db.execute(
            select(UserFeedEntry.post_id)
            .where(UserFeedEntry.user_id == query.viewer_id)
            .order_by(UserFeedEntry.created_at.desc())
            .limit(20)
        )
        post_ids = [row[0] for row in result.all()]
        if not post_ids:
            query.viewer_interest_vector = None
            return query

        result = await db.execute(
            select(PostEmbedding.embedding).where(PostEmbedding.post_id.in_(post_ids))
        )
        embeddings = [row[0] for row in result.all()]
        query.viewer_interest_vector = mean_embedding(embeddings)
        return query


class ThunderSource(Source):
    name = "thunder"
    """Read pre-materialized in-network candidates from user_feed."""

    async def fetch(self, db: AsyncSession, query: FeedQuery) -> list[FeedCandidate]:
        stmt = (
            select(UserFeedEntry, Post)
            .join(Post, Post.id == UserFeedEntry.post_id)
            .where(
                UserFeedEntry.user_id == query.viewer_id,
                Post.deleted_at.is_(None),
                Post.status == PostStatus.PUBLISHED,
            )
            .order_by(UserFeedEntry.created_at.desc(), UserFeedEntry.post_id.desc())
            .limit(query.limit + 1)
        )
        if query.cursor is not None:
            cursor_time, cursor_id = query.cursor
            stmt = stmt.where(
                or_(
                    UserFeedEntry.created_at < cursor_time,
                    and_(
                        UserFeedEntry.created_at == cursor_time,
                        UserFeedEntry.post_id < cursor_id,
                    ),
                )
            )

        result = await db.execute(stmt)
        rows = result.all()
        return [
            FeedCandidate(
                id=post.id,
                author_id=post.author_id,
                body=post.body,
                created_at=entry.created_at,
                visibility=post.visibility,
            )
            for entry, post in rows
        ]


class OutOfNetworkSource(Source):
    name = "oon"

    async def fetch(self, db: AsyncSession, query: FeedQuery) -> list[FeedCandidate]:
        if query.viewer_interest_vector is None:
            return []

        fetch_limit = max(query.limit + 1, int(query.limit * 0.3) + 5)
        rows = await search_similar_posts(db, query, limit=fetch_limit)
        return [
            FeedCandidate(
                id=post.id,
                author_id=post.author_id,
                body=post.body,
                created_at=post.created_at,
                visibility=post.visibility,
                source="oon",
                similarity_score=similarity,
            )
            for post, similarity in rows
        ]


class InNetworkSource(Source):
    name = "in_network"
    async def fetch(self, db: AsyncSession, query: FeedQuery) -> list[FeedCandidate]:
        if not query.following_ids:
            return []

        stmt = (
            select(Post)
            .where(
                Post.author_id.in_(query.following_ids),
                Post.deleted_at.is_(None),
                Post.status == PostStatus.PUBLISHED,
            )
            .order_by(Post.created_at.desc(), Post.id.desc())
            .limit(query.limit + 1)
        )
        if query.cursor is not None:
            cursor_time, cursor_id = query.cursor
            stmt = stmt.where(
                or_(
                    Post.created_at < cursor_time,
                    and_(Post.created_at == cursor_time, Post.id < cursor_id),
                )
            )

        result = await db.execute(stmt)
        posts = result.scalars().all()
        return [
            FeedCandidate(
                id=post.id,
                author_id=post.author_id,
                body=post.body,
                created_at=post.created_at,
                visibility=post.visibility,
            )
            for post in posts
        ]


class AuthorHydrator(Hydrator):
    async def enrich(
        self, db: AsyncSession, query: FeedQuery, candidates: list[FeedCandidate]
    ) -> list[FeedCandidate]:
        if not candidates:
            return candidates

        author_ids = {c.author_id for c in candidates}
        result = await db.execute(select(User).where(User.id.in_(author_ids)))
        authors = {user.id: user for user in result.scalars().all()}

        for candidate in candidates:
            author = authors.get(candidate.author_id)
            if author is None:
                continue
            candidate.author_handle = author.handle
            candidate.author_display_name = author.display_name
            candidate.author_is_private = author.is_private
            candidate.author_status = author.status
        return candidates


class EngagementHydrator(Hydrator):
    async def enrich(
        self, db: AsyncSession, query: FeedQuery, candidates: list[FeedCandidate]
    ) -> list[FeedCandidate]:
        if not candidates:
            return candidates

        post_ids = [c.id for c in candidates]
        result = await db.execute(
            select(PostEngagement).where(PostEngagement.post_id.in_(post_ids))
        )
        engagement_by_post = {row.post_id: row for row in result.scalars().all()}

        for candidate in candidates:
            engagement = engagement_by_post.get(candidate.id)
            if engagement is None:
                continue
            candidate.like_count = engagement.like_count
            candidate.reply_count = engagement.reply_count
        return candidates


class PolicyFilter:
    def __init__(self, rules: list[Rule]):
        self.rules = rules

    async def apply(self, query: FeedQuery, candidates: list[FeedCandidate]) -> list[FeedCandidate]:
        kept: list[FeedCandidate] = []
        drops: list[dict[str, str]] = []

        for candidate in candidates:
            context = PolicyContext(
                viewer_id=query.viewer_id,
                following_ids=query.following_ids,
                blocked_user_ids=query.blocked_user_ids,
                muted_user_ids=query.muted_user_ids,
                muted_keywords=query.muted_keywords,
                candidate=candidate,
            )
            verdict, rule_name = evaluate_rules(self.rules, context)
            if verdict == PolicyVerdict.DROP:
                drops.append(
                    {
                        "post_id": str(candidate.id),
                        "author_id": str(candidate.author_id),
                        "rule": rule_name or "unknown",
                    }
                )
                continue
            kept.append(candidate)

        if drops:
            logger.info(
                "policy_drops",
                viewer_id=str(query.viewer_id),
                dropped_count=len(drops),
                drops=drops[:20],
            )
        return kept


class CursorSelector(Selector):
    def select(
        self, query: FeedQuery, candidates: list[FeedCandidate]
    ) -> tuple[list[FeedCandidate], str | None]:
        has_more = len(candidates) > query.limit
        page = candidates[: query.limit]
        if not has_more or not page:
            return page, None

        last = page[-1]
        return page, encode_cursor(last.created_at, last.id)


class FeedPipeline:
    def __init__(
        self,
        query_hydrators: list[QueryHydrator],
        sources: list[Source],
        hydrators: list[Hydrator],
        policy: PolicyFilter,
        weights: RankingWeights,
        selector: Selector,
        blender: SourceBlender | None = None,
    ):
        self.query_hydrators = query_hydrators
        self.sources = sources
        self.hydrators = hydrators
        self.policy = policy
        self.weights = weights
        self.selector = selector
        self.blender = blender

    async def run(self, db: AsyncSession, query: FeedQuery) -> tuple[list[FeedCandidate], str | None]:
        stage_stats: dict[str, dict[str, float | int]] = {}

        for hydrator in self.query_hydrators:
            start = time.perf_counter()
            query = await hydrator.hydrate(db, query)
            stage_stats[hydrator.__class__.__name__] = {
                "duration_ms": (time.perf_counter() - start) * 1000,
                "following_count": len(query.following_ids),
            }

        batches: dict[str, list[FeedCandidate]] = {}
        for source in self.sources:
            start = time.perf_counter()
            batch = await source.fetch(db, query)
            batches[source.name] = batch
            stage_stats[source.__class__.__name__] = {
                "duration_ms": (time.perf_counter() - start) * 1000,
                "count": len(batch),
            }

        start = time.perf_counter()
        if self.blender is not None:
            candidates = self.blender.blend(query, batches)
            stage_stats["SourceBlender"] = {
                "duration_ms": (time.perf_counter() - start) * 1000,
                "count": len(candidates),
            }
        else:
            candidates = []
            for batch in batches.values():
                candidates.extend(batch)

        for hydrator in self.hydrators:
            start = time.perf_counter()
            candidates = await hydrator.enrich(db, query, candidates)
            stage_stats[hydrator.__class__.__name__] = {
                "duration_ms": (time.perf_counter() - start) * 1000,
                "count": len(candidates),
            }

        start = time.perf_counter()
        before_policy = len(candidates)
        candidates = await self.policy.apply(query, candidates)
        stage_stats["PolicyFilter"] = {
            "duration_ms": (time.perf_counter() - start) * 1000,
            "count_before": before_policy,
            "count_after": len(candidates),
            "dropped": before_policy - len(candidates),
        }

        start = time.perf_counter()
        for candidate in candidates:
            candidate.seen = candidate.id in query.seen_post_ids
        candidates = rank_candidates(query, candidates, self.weights)
        stage_stats["Ranker"] = {
            "duration_ms": (time.perf_counter() - start) * 1000,
            "count": len(candidates),
        }

        start = time.perf_counter()
        selected, next_cursor = self.selector.select(query, candidates)
        stage_stats[self.selector.__class__.__name__] = {
            "duration_ms": (time.perf_counter() - start) * 1000,
            "count": len(selected),
        }

        logger.info("feed_pipeline_complete", viewer_id=str(query.viewer_id), stages=stage_stats)
        return selected, next_cursor


def build_feed_pipeline(weights: RankingWeights | None = None) -> FeedPipeline:
    from app.policy.rules import home_feed_policy

    resolved_weights = weights or load_weights()
    return FeedPipeline(
        query_hydrators=[
            FollowingQueryHydrator(),
            BlockedUserIdsQueryHydrator(),
            MutedUserIdsQueryHydrator(),
            MutedKeywordsQueryHydrator(),
            SeenPostsQueryHydrator(),
            ViewerInterestQueryHydrator(),
        ],
        sources=[ThunderSource(), OutOfNetworkSource()],
        blender=SourceBlender(oon_ratio=0.3),
        hydrators=[AuthorHydrator(), EngagementHydrator()],
        policy=PolicyFilter(home_feed_policy()),
        weights=resolved_weights,
        selector=CursorSelector(),
    )
