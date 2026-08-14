from datetime import UTC, datetime

from app.core.models import PostVisibility, UserStatus
from app.policy.engine import PolicyContext, PolicyVerdict, Rule

MAX_AGE_HOURS = 48


class SelfPostRule(Rule):
    name = "SelfPostRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.author_id == context.viewer_id:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class AgeRule(Rule):
    name = "AgeRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        now = context.now or datetime.now(UTC)
        created_at = context.candidate.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        age_hours = (now - created_at).total_seconds() / 3600.0
        if age_hours > MAX_AGE_HOURS:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class BlockedAuthorRule(Rule):
    name = "BlockedAuthorRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.author_id in context.blocked_user_ids:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class MutedAuthorRule(Rule):
    name = "MutedAuthorRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.author_id in context.muted_user_ids:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class MutedKeywordRule(Rule):
    name = "MutedKeywordRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        body = context.candidate.body.lower()
        for keyword in context.muted_keywords:
            if keyword and keyword in body:
                return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class SuspendedAuthorRule(Rule):
    name = "SuspendedAuthorRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.author_status == UserStatus.SUSPENDED:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class PrivateAccountRule(Rule):
    name = "PrivateAccountRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        author_id = context.candidate.author_id
        if author_id == context.viewer_id:
            return PolicyVerdict.ALLOW
        if not context.candidate.author_is_private:
            return PolicyVerdict.ALLOW
        if author_id in context.following_ids:
            return PolicyVerdict.ALLOW
        return PolicyVerdict.DROP


class FollowersOnlyPostRule(Rule):
    name = "FollowersOnlyPostRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.visibility != PostVisibility.FOLLOWERS_ONLY:
            return PolicyVerdict.ALLOW
        author_id = context.candidate.author_id
        if author_id == context.viewer_id:
            return PolicyVerdict.ALLOW
        if author_id in context.following_ids:
            return PolicyVerdict.ALLOW
        return PolicyVerdict.DROP


def home_feed_policy() -> list[Rule]:
    return [
        SelfPostRule(),
        AgeRule(),
        BlockedAuthorRule(),
        MutedAuthorRule(),
        MutedKeywordRule(),
        SuspendedAuthorRule(),
        PrivateAccountRule(),
        FollowersOnlyPostRule(),
    ]
