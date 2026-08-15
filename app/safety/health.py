"""Agatha / user-cred lite: simple account health from social graph signals."""

from __future__ import annotations

import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Block, Follow, Post, User
from app.core.safety_models import SafetyTargetType
from app.core.social_models import FeedbackKind, Like, PostFeedback
from app.safety.labels import LABEL_DO_NOT_AMPLIFY, LABEL_SPAM_SUSPECT, upsert_label

# Blocks received relative to followers → spam pressure.
SPAM_BLOCK_RATIO = 0.35
# Hide feedback relative to impressions/likes floor.
SPAM_HIDE_RATIO = 0.5
MIN_SIGNALS_FOR_SPAM = 3


async def refresh_user_health(db: AsyncSession, user_id: uuid.UUID) -> float:
    """Recompute cred_score (0–100) and optional account labels."""
    user = await db.get(User, user_id)
    if user is None:
        return 50.0

    follower_count = int(
        await db.scalar(select(func.count()).select_from(Follow).where(Follow.followee_id == user_id))
        or 0
    )
    following_count = int(
        await db.scalar(select(func.count()).select_from(Follow).where(Follow.follower_id == user_id))
        or 0
    )
    blocks_received = int(
        await db.scalar(select(func.count()).select_from(Block).where(Block.blocked_id == user_id))
        or 0
    )
    post_ids = list(
        (
            await db.execute(select(Post.id).where(Post.author_id == user_id, Post.deleted_at.is_(None)))
        ).scalars().all()
    )
    like_count = 0
    hide_count = 0
    if post_ids:
        like_count = int(
            await db.scalar(
                select(func.count()).select_from(Like).where(Like.post_id.in_(post_ids))
            )
            or 0
        )
        hide_count = int(
            await db.scalar(
                select(func.count())
                .select_from(PostFeedback)
                .where(PostFeedback.post_id.in_(post_ids), PostFeedback.kind == FeedbackKind.HIDE)
            )
            or 0
        )

    # Cred: log followers + likes, minus blocks/hides. Age is not required for the lite version.
    positive = math.log1p(follower_count + like_count) + 0.2 * math.log1p(following_count)
    negative = 2.5 * math.log1p(blocks_received) + 1.5 * math.log1p(hide_count)
    raw = 50.0 + 12.0 * positive - 15.0 * negative
    cred = max(0.0, min(100.0, raw))
    user.cred_score = cred

    denom = max(follower_count, 1)
    block_ratio = blocks_received / denom
    hide_ratio = hide_count / max(like_count + hide_count, 1)
    spammy = (
        (blocks_received + hide_count) >= MIN_SIGNALS_FOR_SPAM
        and (block_ratio >= SPAM_BLOCK_RATIO or hide_ratio >= SPAM_HIDE_RATIO)
    ) or cred < 25.0

    if spammy:
        await upsert_label(
            db,
            target_type=SafetyTargetType.USER,
            target_id=user_id,
            label=LABEL_SPAM_SUSPECT,
            reason=(
                f"blocks_received={blocks_received} hide_count={hide_count} "
                f"cred={cred:.1f}"
            ),
        )
        await upsert_label(
            db,
            target_type=SafetyTargetType.USER,
            target_id=user_id,
            label=LABEL_DO_NOT_AMPLIFY,
            reason="account spam_suspect",
        )

    await db.commit()
    return cred
