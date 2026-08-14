import math
from datetime import UTC, datetime
from uuid import UUID

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
        + weights.not_interested_author
        * (1.0 if candidate.author_id in query.not_interested_author_ids else 0.0)
    )


def apply_author_diversity(
    candidates: list[FeedCandidate],
    *,
    decay: float,
    floor: float,
) -> list[FeedCandidate]:
    """Attenuate repeated authors after independent scoring.

    Walks candidates in current score order so the strongest post from an
    author keeps factor 1.0. Each later post is multiplied by decay**n,
    clamped to floor, then the list is re-sorted.
    """
    seen_count: dict[UUID, int] = {}
    for candidate in candidates:
        count = seen_count.get(candidate.author_id, 0)
        factor = max(floor, decay**count)
        if candidate.rank_score is not None:
            candidate.rank_score *= factor
        seen_count[candidate.author_id] = count + 1
    return sorted(candidates, key=lambda c: c.rank_score or 0.0, reverse=True)


def rank_candidates(
    query: FeedQuery,
    candidates: list[FeedCandidate],
    weights: RankingWeights,
    *,
    now: datetime | None = None,
) -> list[FeedCandidate]:
    for candidate in candidates:
        candidate.rank_score = score_candidate(query, candidate, weights, now=now)
    ordered = sorted(candidates, key=lambda c: c.rank_score or 0.0, reverse=True)
    return apply_author_diversity(
        ordered,
        decay=weights.author_diversity_decay,
        floor=weights.author_diversity_floor,
    )
