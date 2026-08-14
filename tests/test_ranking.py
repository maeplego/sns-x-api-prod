from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.ranking.scorer import rank_candidates, score_candidate
from app.ranking.weights import RankingWeights
from app.request.feed.types import FeedCandidate, FeedQuery


def test_recency_weight_changes_order():
    viewer_id = uuid4()
    author_id = uuid4()
    now = datetime.now(UTC)

    older = FeedCandidate(
        id=uuid4(),
        author_id=author_id,
        body="older",
        created_at=now - timedelta(hours=24),
    )
    newer = FeedCandidate(
        id=uuid4(),
        author_id=author_id,
        body="newer",
        created_at=now - timedelta(hours=1),
    )
    query = FeedQuery(viewer_id=viewer_id, following_ids={author_id, viewer_id})

    recency_heavy = RankingWeights(
        recency=1.0,
        in_network_boost=0.0,
        engagement=0.0,
        author_affinity=0.0,
        similarity=0.0,
        seen_penalty=0.0,
        author_diversity_decay=1.0,
        author_diversity_floor=1.0,
    )
    ranked = rank_candidates(query, [older, newer], recency_heavy, now=now)
    assert ranked[0].body == "newer"
    assert score_candidate(query, newer, recency_heavy, now=now) > score_candidate(
        query, older, recency_heavy, now=now
    )


def _neutral_weights(**overrides: float) -> RankingWeights:
    values = dict(
        recency=0.0,
        in_network_boost=0.0,
        engagement=0.0,
        author_affinity=0.0,
        similarity=0.0,
        seen_penalty=0.0,
        author_diversity_decay=0.5,
        author_diversity_floor=0.25,
    )
    values.update(overrides)
    return RankingWeights(**values)


def test_author_diversity_lets_other_authors_interrupt_a_streak():
    viewer_id = uuid4()
    author_a = uuid4()
    author_b = uuid4()
    now = datetime.now(UTC)

    a1 = FeedCandidate(
        id=uuid4(),
        author_id=author_a,
        body="a1",
        created_at=now,
        similarity_score=1.0,
    )
    a2 = FeedCandidate(
        id=uuid4(),
        author_id=author_a,
        body="a2",
        created_at=now,
        similarity_score=0.9,
    )
    b1 = FeedCandidate(
        id=uuid4(),
        author_id=author_b,
        body="b1",
        created_at=now,
        similarity_score=0.8,
    )
    query = FeedQuery(viewer_id=viewer_id, following_ids={author_a, author_b, viewer_id})
    weights = _neutral_weights(similarity=1.0)

    ranked = rank_candidates(query, [a1, a2, b1], weights, now=now)
    assert [c.body for c in ranked] == ["a1", "b1", "a2"]
    assert ranked[1].rank_score == ranked[1].similarity_score
    assert ranked[2].rank_score == 0.9 * 0.5

