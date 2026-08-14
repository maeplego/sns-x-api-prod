from datetime import UTC, datetime
from uuid import uuid4

from app.request.feed.blender import SourceBlender
from app.request.feed.types import FeedCandidate, FeedQuery


def _candidate(body: str) -> FeedCandidate:
    return FeedCandidate(
        id=uuid4(),
        author_id=uuid4(),
        body=body,
        created_at=datetime.now(UTC),
    )


def test_blender_dedupes_thunder_over_oon():
    shared_id = uuid4()
    thunder = FeedCandidate(
        id=shared_id,
        author_id=uuid4(),
        body="in network",
        created_at=datetime.now(UTC),
    )
    oon = FeedCandidate(
        id=shared_id,
        author_id=uuid4(),
        body="duplicate",
        created_at=datetime.now(UTC),
        similarity_score=0.99,
    )
    query = FeedQuery(viewer_id=uuid4(), limit=20)
    blender = SourceBlender(oon_ratio=0.5)

    merged = blender.blend(query, {"thunder": [thunder], "oon": [oon]})

    assert len(merged) == 1
    assert merged[0].source == "thunder"


def test_blender_caps_oon_ratio():
    query = FeedQuery(viewer_id=uuid4(), limit=10)
    blender = SourceBlender(oon_ratio=0.3)
    thunder = [_candidate(f"t{i}") for i in range(5)]
    oon = [_candidate(f"o{i}") for i in range(10)]

    merged = blender.blend(query, {"thunder": thunder, "oon": oon})

    oon_count = sum(1 for c in merged if c.source == "oon")
    assert oon_count == 3
    assert len(merged) == 8
