from datetime import UTC, datetime
from uuid import uuid4

from app.request.feed.pipeline import dedupe_conversations
from app.request.feed.types import FeedCandidate


def _post(*, body: str, parent_id=None, root_id=None, score: float = 0.0) -> FeedCandidate:
    post_id = uuid4()
    return FeedCandidate(
        id=post_id,
        author_id=uuid4(),
        body=body,
        created_at=datetime.now(UTC),
        parent_id=parent_id,
        root_id=root_id,
        rank_score=score,
    )


def test_dedupe_keeps_root_and_drops_replies_in_same_conversation():
    root = _post(body="root", score=0.4)
    reply = _post(body="reply", parent_id=root.id, root_id=root.id, score=0.9)
    kept = dedupe_conversations([reply, root])
    assert [c.body for c in kept] == ["root"]


def test_dedupe_keeps_one_orphan_reply_when_root_absent():
    root_id = uuid4()
    hot = _post(body="hot", parent_id=uuid4(), root_id=root_id, score=0.8)
    cold = _post(body="cold", parent_id=uuid4(), root_id=root_id, score=0.2)
    kept = dedupe_conversations([hot, cold])
    assert [c.body for c in kept] == ["hot"]
