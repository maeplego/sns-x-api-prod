from datetime import UTC, datetime
from uuid import uuid4

from app.core.models import PostVisibility, UserStatus
from app.policy.engine import PolicyContext, PolicyVerdict, evaluate_rules
from app.policy.rules import OonAmplificationRule, home_feed_policy
from app.request.feed.types import FeedCandidate


def test_oon_amplification_drops_labeled_posts():
    viewer = uuid4()
    author = uuid4()
    candidate = FeedCandidate(
        id=uuid4(),
        author_id=author,
        body="spammy",
        created_at=datetime.now(UTC),
        source="oon",
        safety_labels={"do_not_amplify"},
    )
    context = PolicyContext(
        viewer_id=viewer,
        following_ids=set(),
        blocked_user_ids=set(),
        candidate=candidate,
    )
    verdict, rule = evaluate_rules([OonAmplificationRule()], context)
    assert verdict == PolicyVerdict.DROP
    assert rule == "OonAmplificationRule"


def test_in_network_keeps_labeled_posts():
    viewer = uuid4()
    author = uuid4()
    candidate = FeedCandidate(
        id=uuid4(),
        author_id=author,
        body="nsfw but followed",
        created_at=datetime.now(UTC),
        source="thunder",
        visibility=PostVisibility.PUBLIC,
        author_status=UserStatus.ACTIVE,
        safety_labels={"nsfw", "do_not_amplify"},
    )
    context = PolicyContext(
        viewer_id=viewer,
        following_ids={author},
        blocked_user_ids=set(),
        candidate=candidate,
    )
    verdict, _ = evaluate_rules(home_feed_policy(), context)
    assert verdict == PolicyVerdict.ALLOW


def test_oon_amplification_drops_author_labels():
    viewer = uuid4()
    author = uuid4()
    candidate = FeedCandidate(
        id=uuid4(),
        author_id=author,
        body="from spam account",
        created_at=datetime.now(UTC),
        source="oon",
        author_safety_labels={"spam_suspect"},
    )
    context = PolicyContext(
        viewer_id=viewer,
        following_ids=set(),
        blocked_user_ids=set(),
        candidate=candidate,
    )
    verdict, rule = evaluate_rules([OonAmplificationRule()], context)
    assert verdict == PolicyVerdict.DROP
    assert rule == "OonAmplificationRule"
