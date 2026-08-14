import math
from datetime import UTC, datetime

from app.ranking.weights import RankingWeights
from app.request.feed.types import FeedCandidate, FeedQuery


def recency_signal(created_at: datetime, *, now: datetime | None = None) -> float:
    reference = now or datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    age_hours = max((reference - created_at).total_seconds() / 3600.0, 0.0)
    return 1.0 / (1.0 + age_hours)


def engagement_signal(like_count: int, reply_count: int) -> float:
    return math.log1p(max(like_count, 0) + max(reply_count, 0))


def score_candidate(
    query: FeedQuery,
    candidate: FeedCandidate,
    weights: RankingWeights,
    *,
    now: datetime | None = None,
) -> float:
    in_network = (
        1.0
        if candidate.author_id in query.following_ids and candidate.author_id != query.viewer_id
        else 0.0
    )
    return (
        weights.recency * recency_signal(candidate.created_at, now=now)
        + weights.in_network_boost * in_network
        + weights.engagement * engagement_signal(candidate.like_count, candidate.reply_count)
        + weights.author_affinity * candidate.author_affinity
        + weights.similarity * (candidate.similarity_score or 0.0)
        + weights.seen_penalty * (1.0 if candidate.seen else 0.0)
    )


def rank_candidates(
    query: FeedQuery,
    candidates: list[FeedCandidate],
    weights: RankingWeights,
    *,
    now: datetime | None = None,
) -> list[FeedCandidate]:
    return sorted(
        candidates,
        key=lambda c: score_candidate(query, c, weights, now=now),
        reverse=True,
    )
