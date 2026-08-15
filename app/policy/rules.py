from datetime import UTC, datetime

from app.core.models import PostVisibility, UserStatus
from app.policy.engine import PolicyContext, PolicyVerdict, Rule

MAX_AGE_HOURS = 48


class HiddenPostRule(Rule):
    name = "HiddenPostRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.id in context.hidden_post_ids:
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


class OonReplyRule(Rule):
    name = "OonReplyRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        candidate = context.candidate
        if candidate.parent_id is None:
            return PolicyVerdict.ALLOW
        if candidate.source == "oon":
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class ReplyAncillaryRule(Rule):
    """Drop a reply when its parent would be invisible (x-algorithm AncillaryVF)."""

    name = "ReplyAncillaryRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        candidate = context.candidate
        if candidate.parent_id is None:
            return PolicyVerdict.ALLOW
        if candidate.parent_missing or candidate.parent_author_id is None:
            return PolicyVerdict.DROP
        parent_author_id = candidate.parent_author_id
        if parent_author_id in context.blocked_user_ids:
            return PolicyVerdict.DROP
        if parent_author_id in context.muted_user_ids:
            return PolicyVerdict.DROP
        if candidate.parent_author_status == UserStatus.SUSPENDED:
            return PolicyVerdict.DROP
        if parent_author_id == context.viewer_id:
            return PolicyVerdict.ALLOW
        if candidate.parent_author_is_private and parent_author_id not in context.following_ids:
            return PolicyVerdict.DROP
        if (
            candidate.parent_visibility == PostVisibility.FOLLOWERS_ONLY
            and parent_author_id not in context.following_ids
        ):
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class OonAmplificationRule(Rule):
    """Drop OON candidates with amplification-limiting safety labels (X-style)."""

    name = "OonAmplificationRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        candidate = context.candidate
        if candidate.source != "oon":
            return PolicyVerdict.ALLOW
        labels = candidate.safety_labels | candidate.author_safety_labels
        if labels & {"spam_suspect", "nsfw", "do_not_amplify"}:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


def home_feed_policy() -> list[Rule]:
    return [
        HiddenPostRule(),
        AgeRule(),
        BlockedAuthorRule(),
        MutedAuthorRule(),
        MutedKeywordRule(),
        SuspendedAuthorRule(),
        PrivateAccountRule(),
        FollowersOnlyPostRule(),
        OonReplyRule(),
        OonAmplificationRule(),
        ReplyAncillaryRule(),
    ]


def following_feed_policy() -> list[Rule]:
    """Chronological Following surface: no 48h cutoff, no OON reply rule."""
    return [
        HiddenPostRule(),
        BlockedAuthorRule(),
        MutedAuthorRule(),
        MutedKeywordRule(),
        SuspendedAuthorRule(),
        PrivateAccountRule(),
        FollowersOnlyPostRule(),
        ReplyAncillaryRule(),
    ]


def thread_policy() -> list[Rule]:
    """Thread view shows own posts and old posts; it still hides blocks/mutes."""
    return [
        BlockedAuthorRule(),
        MutedAuthorRule(),
        MutedKeywordRule(),
        SuspendedAuthorRule(),
        PrivateAccountRule(),
        FollowersOnlyPostRule(),
    ]
