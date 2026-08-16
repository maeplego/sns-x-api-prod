import enum
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from app.request.feed.types import FeedCandidate


class PolicyVerdict(str, enum.Enum):
    ALLOW = "allow"
    DROP = "drop"
    INTERSTITIAL = "interstitial"


@dataclass(frozen=True)
class PolicyContext:
    viewer_id: uuid.UUID
    following_ids: set[uuid.UUID]
    blocked_user_ids: set[uuid.UUID]
    candidate: FeedCandidate
    muted_user_ids: set[uuid.UUID] = field(default_factory=set)
    muted_keywords: set[str] = field(default_factory=set)
    hidden_post_ids: set[uuid.UUID] = field(default_factory=set)
    now: datetime | None = None
    viewer_birthdate: date | None = None


class Rule:
    name: str

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        raise NotImplementedError


def evaluate_rules(
    rules: list[Rule], context: PolicyContext
) -> tuple[PolicyVerdict, str | None]:
    """DROP wins immediately. Otherwise the first INTERSTITIAL is kept."""
    interstitial_from: str | None = None
    for rule in rules:
        verdict = rule.evaluate(context)
        if verdict == PolicyVerdict.DROP:
            return PolicyVerdict.DROP, rule.name
        if verdict == PolicyVerdict.INTERSTITIAL and interstitial_from is None:
            interstitial_from = rule.name
    if interstitial_from is not None:
        return PolicyVerdict.INTERSTITIAL, interstitial_from
    return PolicyVerdict.ALLOW, None
