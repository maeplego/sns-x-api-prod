from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.models import PostVisibility
from app.policy.engine import PolicyContext, PolicyVerdict, evaluate_rules
from app.policy.rules import (
    MAX_AGE_HOURS,
    AgeRule,
    MutedAuthorRule,
    MutedKeywordRule,
    following_feed_policy,
    home_feed_policy,
)
from app.request.feed.types import FeedCandidate


def _candidate(**overrides) -> FeedCandidate:
    values = dict(
        id=uuid4(),
        author_id=uuid4(),
        body="hello world",
        created_at=datetime.now(UTC),
        visibility=PostVisibility.PUBLIC,
    )
    values.update(overrides)
    return FeedCandidate(**values)


def test_age_rule_drops_posts_older_than_48_hours():
    viewer_id = uuid4()
    now = datetime.now(UTC)
    old = _candidate(created_at=now - timedelta(hours=MAX_AGE_HOURS, seconds=1))
    fresh = _candidate(created_at=now - timedelta(hours=MAX_AGE_HOURS) + timedelta(minutes=1))
    old_ctx = PolicyContext(
        viewer_id=viewer_id,
        following_ids=set(),
        blocked_user_ids=set(),
        candidate=old,
        now=now,
    )
    fresh_ctx = PolicyContext(
        viewer_id=viewer_id,
        following_ids=set(),
        blocked_user_ids=set(),
        candidate=fresh,
        now=now,
    )
    assert AgeRule().evaluate(old_ctx) == PolicyVerdict.DROP
    assert AgeRule().evaluate(fresh_ctx) == PolicyVerdict.ALLOW


def test_muted_author_and_keyword_rules():
    viewer_id = uuid4()
    muted_id = uuid4()
    author_ctx = PolicyContext(
        viewer_id=viewer_id,
        following_ids={muted_id},
        blocked_user_ids=set(),
        muted_user_ids={muted_id},
        candidate=_candidate(author_id=muted_id, body="normal post"),
    )
    keyword_ctx = PolicyContext(
        viewer_id=viewer_id,
        following_ids=set(),
        blocked_user_ids=set(),
        muted_keywords={"spam"},
        candidate=_candidate(body="This is SPAM content"),
    )
    assert MutedAuthorRule().evaluate(author_ctx) == PolicyVerdict.DROP
    assert MutedKeywordRule().evaluate(keyword_ctx) == PolicyVerdict.DROP


def test_home_and_following_policies_keep_viewer_own_post():
    viewer_id = uuid4()
    candidate = _candidate(author_id=viewer_id, body="my post")
    context = PolicyContext(
        viewer_id=viewer_id,
        following_ids={viewer_id},
        blocked_user_ids=set(),
        candidate=candidate,
    )
    home_verdict, home_rule = evaluate_rules(home_feed_policy(), context)
    following_verdict, following_rule = evaluate_rules(following_feed_policy(), context)
    assert home_verdict == PolicyVerdict.ALLOW
    assert home_rule is None
    assert following_verdict == PolicyVerdict.ALLOW
    assert following_rule is None
