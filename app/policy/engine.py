import enum
import uuid
from dataclasses import dataclass

from app.core.models import UserStatus
from app.request.feed.types import FeedCandidate


class PolicyVerdict(str, enum.Enum):
    ALLOW = "allow"
    DROP = "drop"


@dataclass(frozen=True)
class PolicyContext:
    viewer_id: uuid.UUID
    following_ids: set[uuid.UUID]
    blocked_user_ids: set[uuid.UUID]
    candidate: FeedCandidate


class Rule:
    name: str

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        raise NotImplementedError


def evaluate_rules(
    rules: list[Rule], context: PolicyContext
) -> tuple[PolicyVerdict, str | None]:
    for rule in rules:
        if rule.evaluate(context) == PolicyVerdict.DROP:
            return PolicyVerdict.DROP, rule.name
    return PolicyVerdict.ALLOW, None
