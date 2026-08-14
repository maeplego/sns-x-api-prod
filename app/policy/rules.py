from app.core.models import PostVisibility, UserStatus
from app.policy.engine import PolicyContext, PolicyVerdict, Rule


class BlockedAuthorRule(Rule):
    name = "BlockedAuthorRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.author_id in context.blocked_user_ids:
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
        BlockedAuthorRule(),
        SuspendedAuthorRule(),
        PrivateAccountRule(),
        FollowersOnlyPostRule(),
    ]
