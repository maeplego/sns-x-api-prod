from datetime import date, timedelta

from app.core.age import age_years, is_adult
from app.core.models import PostVisibility, UserStatus
from app.policy.engine import PolicyContext, PolicyVerdict, evaluate_rules
from app.policy.rules import SensitiveInterstitialRule, ViewerAgeGateRule
from app.request.feed.types import FeedCandidate
import uuid
from datetime import datetime, UTC


def _candidate(**overrides) -> FeedCandidate:
    values = dict(
        id=uuid.uuid4(),
        author_id=uuid.uuid4(),
        body="hello #nsfw maybe",
        created_at=datetime.now(UTC),
        visibility=PostVisibility.PUBLIC,
        author_status=UserStatus.ACTIVE,
        source="in_network",
        safety_labels={"nsfw"},
    )
    values.update(overrides)
    return FeedCandidate(**values)


def _ctx(candidate: FeedCandidate, birthdate: date | None) -> PolicyContext:
    return PolicyContext(
        viewer_id=uuid.uuid4(),
        following_ids=set(),
        blocked_user_ids=set(),
        candidate=candidate,
        viewer_birthdate=birthdate,
    )


def test_age_years_and_adult():
    today = date(2026, 8, 17)
    assert age_years(date(2010, 8, 17), today=today) == 16
    assert not is_adult(date(2010, 8, 17), today=today)
    assert is_adult(date(2000, 1, 1), today=today)
    assert is_adult(None)


def test_viewer_age_gate_drops_nsfw_for_minors():
    minor = date.today() - timedelta(days=365 * 16)
    adult = date.today() - timedelta(days=365 * 20)
    candidate = _candidate()
    assert ViewerAgeGateRule().evaluate(_ctx(candidate, minor)) == PolicyVerdict.DROP
    assert ViewerAgeGateRule().evaluate(_ctx(candidate, adult)) == PolicyVerdict.ALLOW


def test_interstitial_for_adult_in_network_nsfw():
    adult = date.today() - timedelta(days=365 * 25)
    candidate = _candidate(source="in_network")
    assert SensitiveInterstitialRule().evaluate(_ctx(candidate, adult)) == PolicyVerdict.INTERSTITIAL
    oon = _candidate(source="oon")
    assert SensitiveInterstitialRule().evaluate(_ctx(oon, adult)) == PolicyVerdict.ALLOW


def test_evaluate_rules_interstitial_after_allows():
    adult = date.today() - timedelta(days=365 * 25)
    candidate = _candidate()
    verdict, rule = evaluate_rules(
        [ViewerAgeGateRule(), SensitiveInterstitialRule()],
        _ctx(candidate, adult),
    )
    assert verdict == PolicyVerdict.INTERSTITIAL
    assert rule == "SensitiveInterstitialRule"
