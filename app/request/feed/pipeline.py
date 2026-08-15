import time
import uuid
from abc import ABC, abstractmethod

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding_models import PostEmbedding
from app.core.models import Block, Follow, Mute, Post, PostEngagement, PostStatus, User
from app.core.safety_models import SafetyTargetType
from app.core.social_models import FeedImpression, FeedbackKind, Like, MutedKeyword, PostFeedback, UserFeedEntry
from app.embedding.encoder import mean_embedding
from app.embedding.search import search_similar_posts
from app.policy.engine import PolicyContext, PolicyVerdict, Rule, evaluate_rules
from app.ranking.scorer import rank_candidates
from app.ranking.weights import RankingWeights, load_weights
from app.request.feed.blender import SourceBlender
from app.request.feed.types import FeedCandidate, FeedQuery, ReferencedPost, encode_cursor
from app.safety.labels import labels_for_targets

logger = structlog.get_logger(__name__)


def _from_post(post: Post, **overrides) -> FeedCandidate:
    values = dict(
        id=post.id,
        author_id=post.author_id,
        body=post.body,
        created_at=post.created_at,
        visibility=post.visibility,
        parent_id=post.parent_id,
        root_id=post.root_id,
        quote_of_id=post.quote_of_id,
        repost_of_id=post.repost_of_id,
    )
    values.update(overrides)
    return FeedCandidate(**values)


def dedupe_conversations(candidates: list[FeedCandidate]) -> list[FeedCandidate]:
    """Keep the root when present; otherwise keep the top-scored orphan reply.

    Matches x-algorithm DedupConversationFilter at personal scale: one item
    per conversation in the For You page.
    """
    conversations_with_root = {c.root_id or c.id for c in candidates if c.parent_id is None}
    orphan_kept: set = set()
    kept: list[FeedCandidate] = []
    for candidate in candidates:
        conversation_id = candidate.root_id or candidate.id
        if candidate.parent_id is None:
            kept.append(candidate)
            continue
        if conversation_id in conversations_with_root:
            continue
        if conversation_id in orphan_kept:
            continue
        orphan_kept.add(conversation_id)
        kept.append(candidate)
    return kept


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


class FeedbackQueryHydrator(QueryHydrator):
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery:
        result = await db.execute(
            select(PostFeedback, Post)
            .join(Post, Post.id == PostFeedback.post_id)
            .where(PostFeedback.viewer_id == query.viewer_id)
        )
        hidden: set = set()
        not_interested_authors: set = set()
        for feedback, post in result.all():
            hidden.add(feedback.post_id)
            if feedback.kind == FeedbackKind.NOT_INTERESTED:
                not_interested_authors.add(post.author_id)
        query.hidden_post_ids = hidden
        query.not_interested_author_ids = not_interested_authors
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
            .join(Post, Post.id == UserFeedEntry.post_id)
            .where(
                UserFeedEntry.user_id == query.viewer_id,
                Post.parent_id.is_(None),
            )
            .order_by(UserFeedEntry.created_at.desc())
            .limit(20)
        )
        post_ids = [row[0] for row in result.all()]
        if not post_ids:
            query.viewer_interest_vector = None
            return query

        try:
            result = await db.execute(
                select(PostEmbedding.embedding).where(PostEmbedding.post_id.in_(post_ids))
            )
            embeddings = [row[0] for row in result.all()]
            query.viewer_interest_vector = mean_embedding(embeddings)
        except Exception:
            logger.exception("viewer_interest_failed")
            query.viewer_interest_vector = None
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
            _from_post(post, created_at=entry.created_at)
            for entry, post in rows
        ]


class OutOfNetworkSource(Source):
    name = "oon"

    async def fetch(self, db: AsyncSession, query: FeedQuery) -> list[FeedCandidate]:
        if query.viewer_interest_vector is None:
            return []

        fetch_limit = max(query.limit + 1, int(query.limit * 0.3) + 5)
        try:
            rows = await search_similar_posts(db, query, limit=fetch_limit)
        except Exception:
            logger.exception("oon_search_failed")
            return []
        return [
            _from_post(post, source="oon", similarity_score=similarity)
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
        return [_from_post(post) for post in posts]


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
            candidate.author_cred_score = float(author.cred_score)
        return candidates


class SafetyLabelHydrator(Hydrator):
    async def enrich(
        self, db: AsyncSession, query: FeedQuery, candidates: list[FeedCandidate]
    ) -> list[FeedCandidate]:
        if not candidates:
            return candidates
        post_ids = {c.id for c in candidates}
        author_ids = {c.author_id for c in candidates}
        post_labels = await labels_for_targets(
            db, target_type=SafetyTargetType.POST, target_ids=post_ids
        )
        author_labels = await labels_for_targets(
            db, target_type=SafetyTargetType.USER, target_ids=author_ids
        )
        for candidate in candidates:
            candidate.safety_labels = post_labels.get(candidate.id, set())
            candidate.author_safety_labels = author_labels.get(candidate.author_id, set())
        return candidates


class ParentHydrator(Hydrator):
    async def enrich(
        self, db: AsyncSession, query: FeedQuery, candidates: list[FeedCandidate]
    ) -> list[FeedCandidate]:
        parent_ids = {c.parent_id for c in candidates if c.parent_id is not None}
        if not parent_ids:
            return candidates

        result = await db.execute(select(Post).where(Post.id.in_(parent_ids)))
        parents = {post.id: post for post in result.scalars().all()}
        author_ids = {post.author_id for post in parents.values()}
        authors: dict = {}
        if author_ids:
            author_result = await db.execute(select(User).where(User.id.in_(author_ids)))
            authors = {user.id: user for user in author_result.scalars().all()}

        for candidate in candidates:
            if candidate.parent_id is None:
                continue
            parent = parents.get(candidate.parent_id)
            if parent is None or parent.deleted_at is not None or parent.status != PostStatus.PUBLISHED:
                candidate.parent_missing = True
                continue
            candidate.parent_author_id = parent.author_id
            candidate.parent_visibility = parent.visibility
            author = authors.get(parent.author_id)
            if author is not None:
                candidate.parent_author_handle = author.handle
                candidate.parent_author_is_private = author.is_private
                candidate.parent_author_status = author.status
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
            candidate.repost_count = engagement.repost_count
        return candidates


class ReferenceHydrator(Hydrator):
    async def enrich(
        self, db: AsyncSession, query: FeedQuery, candidates: list[FeedCandidate]
    ) -> list[FeedCandidate]:
        ref_ids = {c.quote_of_id for c in candidates if c.quote_of_id} | {
            c.repost_of_id for c in candidates if c.repost_of_id
        }
        if not ref_ids:
            return candidates

        result = await db.execute(select(Post).where(Post.id.in_(ref_ids)))
        posts = {post.id: post for post in result.scalars().all()}
        author_ids = {post.author_id for post in posts.values()}
        authors: dict = {}
        if author_ids:
            author_result = await db.execute(select(User).where(User.id.in_(author_ids)))
            authors = {user.id: user for user in author_result.scalars().all()}
        engagements: dict = {}
        eng_result = await db.execute(
            select(PostEngagement).where(PostEngagement.post_id.in_(ref_ids))
        )
        engagements = {row.post_id: row for row in eng_result.scalars().all()}

        def to_ref(post_id: uuid.UUID | None) -> ReferencedPost | None:
            if post_id is None:
                return None
            post = posts.get(post_id)
            if post is None or post.deleted_at is not None:
                return ReferencedPost(
                    id=post_id,
                    author_id=None,
                    author_handle="deleted",
                    author_display_name="削除済み",
                    body="",
                )
            author = authors.get(post.author_id)
            return ReferencedPost(
                id=post.id,
                author_id=post.author_id,
                author_handle=author.handle if author is not None else "unknown",
                author_display_name=author.display_name if author is not None else "Unknown",
                body=post.body,
            )

        for candidate in candidates:
            candidate.quote_of = to_ref(candidate.quote_of_id)
            candidate.repost_of = to_ref(candidate.repost_of_id)
            if candidate.repost_of_id is not None:
                engagement = engagements.get(candidate.repost_of_id)
                if engagement is not None:
                    candidate.like_count = engagement.like_count
                    candidate.reply_count = engagement.reply_count
                    candidate.repost_count = engagement.repost_count
        return candidates


class ViewerStateHydrator(Hydrator):
    async def enrich(
        self, db: AsyncSession, query: FeedQuery, candidates: list[FeedCandidate]
    ) -> list[FeedCandidate]:
        if not candidates:
            return candidates
        target_ids = {c.repost_of_id or c.id for c in candidates}
        like_rows = await db.execute(
            select(Like.post_id).where(
                Like.user_id == query.viewer_id,
                Like.post_id.in_(target_ids),
            )
        )
        liked_ids = {row[0] for row in like_rows.all()}
        repost_rows = await db.execute(
            select(Post.repost_of_id).where(
                Post.author_id == query.viewer_id,
                Post.repost_of_id.in_(target_ids),
                Post.deleted_at.is_(None),
                Post.status == PostStatus.PUBLISHED,
            )
        )
        reposted_ids = {row[0] for row in repost_rows.all() if row[0] is not None}
        for candidate in candidates:
            original = candidate.repost_of_id or candidate.id
            candidate.liked = original in liked_ids
            candidate.reposted = original in reposted_ids
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
                hidden_post_ids=query.hidden_post_ids,
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
        conversation_deduper: bool = True,
        rank: bool = True,
    ):
        self.query_hydrators = query_hydrators
        self.sources = sources
        self.hydrators = hydrators
        self.policy = policy
        self.weights = weights
        self.selector = selector
        self.blender = blender
        self.conversation_deduper = conversation_deduper
        self.rank = rank

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
        if self.rank:
            for candidate in candidates:
                candidate.seen = candidate.id in query.seen_post_ids
            candidates = rank_candidates(query, candidates, self.weights)
            stage_stats["Ranker"] = {
                "duration_ms": (time.perf_counter() - start) * 1000,
                "count": len(candidates),
            }
        else:
            candidates.sort(key=lambda c: (c.created_at, c.id), reverse=True)
            stage_stats["ChronologicalSort"] = {
                "duration_ms": (time.perf_counter() - start) * 1000,
                "count": len(candidates),
            }

        if self.conversation_deduper:
            start = time.perf_counter()
            before_dedupe = len(candidates)
            candidates = dedupe_conversations(candidates)
            stage_stats["ConversationDeduper"] = {
                "duration_ms": (time.perf_counter() - start) * 1000,
                "count_before": before_dedupe,
                "count_after": len(candidates),
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
            FeedbackQueryHydrator(),
            SeenPostsQueryHydrator(),
            ViewerInterestQueryHydrator(),
        ],
        sources=[ThunderSource(), OutOfNetworkSource()],
        blender=SourceBlender(oon_ratio=0.35),
        hydrators=[
            AuthorHydrator(),
            SafetyLabelHydrator(),
            ParentHydrator(),
            EngagementHydrator(),
            ReferenceHydrator(),
            ViewerStateHydrator(),
        ],
        policy=PolicyFilter(home_feed_policy()),
        weights=resolved_weights,
        selector=CursorSelector(),
    )


def build_following_pipeline(weights: RankingWeights | None = None) -> FeedPipeline:
    from app.policy.rules import following_feed_policy

    resolved_weights = weights or load_weights()
    return FeedPipeline(
        query_hydrators=[
            FollowingQueryHydrator(),
            BlockedUserIdsQueryHydrator(),
            MutedUserIdsQueryHydrator(),
            MutedKeywordsQueryHydrator(),
            FeedbackQueryHydrator(),
        ],
        sources=[ThunderSource()],
        hydrators=[
            AuthorHydrator(),
            ParentHydrator(),
            EngagementHydrator(),
            ReferenceHydrator(),
            ViewerStateHydrator(),
        ],
        policy=PolicyFilter(following_feed_policy()),
        weights=resolved_weights,
        selector=CursorSelector(),
        blender=None,
        conversation_deduper=False,
        rank=False,
    )
