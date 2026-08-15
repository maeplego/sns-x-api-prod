"""Safety labels and indie Visibility Filtering helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safety_models import SafetyLabel, SafetyTargetType

LABEL_SPAM_SUSPECT = "spam_suspect"
LABEL_NSFW = "nsfw"
LABEL_DO_NOT_AMPLIFY = "do_not_amplify"

OON_DROP_LABELS = frozenset({LABEL_SPAM_SUSPECT, LABEL_NSFW, LABEL_DO_NOT_AMPLIFY})

LABEL_EFFECTS: dict[str, str] = {
    LABEL_SPAM_SUSPECT: "フォロー外の推薦（For You の OON）から除外されます。",
    LABEL_NSFW: "成人向けと判定され、フォロー外の推薦から除外されます。",
    LABEL_DO_NOT_AMPLIFY: "拡散制限のため、フォロー外の推薦から除外されます。",
}


async def upsert_label(
    db: AsyncSession,
    *,
    target_type: SafetyTargetType,
    target_id: uuid.UUID,
    label: str,
    reason: str,
) -> SafetyLabel:
    existing = await db.scalar(
        select(SafetyLabel).where(
            SafetyLabel.target_type == target_type,
            SafetyLabel.target_id == target_id,
            SafetyLabel.label == label,
        )
    )
    if existing is not None:
        existing.reason = reason
        existing.created_at = datetime.now(UTC)
        return existing
    row = SafetyLabel(
        target_type=target_type,
        target_id=target_id,
        label=label,
        reason=reason,
    )
    db.add(row)
    return row


async def labels_for_targets(
    db: AsyncSession,
    *,
    target_type: SafetyTargetType,
    target_ids: set[uuid.UUID],
) -> dict[uuid.UUID, set[str]]:
    if not target_ids:
        return {}
    rows = await db.execute(
        select(SafetyLabel.target_id, SafetyLabel.label).where(
            SafetyLabel.target_type == target_type,
            SafetyLabel.target_id.in_(target_ids),
        )
    )
    out: dict[uuid.UUID, set[str]] = {tid: set() for tid in target_ids}
    for target_id, label in rows.all():
        out.setdefault(target_id, set()).add(label)
    return out
