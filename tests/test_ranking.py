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
        seen_penalty=0.0,
    )
    ranked = rank_candidates(query, [older, newer], recency_heavy, now=now)
    assert ranked[0].body == "newer"
    assert score_candidate(query, newer, recency_heavy, now=now) > score_candidate(
        query, older, recency_heavy, now=now
    )
