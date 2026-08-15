from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Post, User
from app.core.safety_models import SafetyLabel, SafetyTargetType
from app.request.auth import get_current_user
from app.safety.health import refresh_user_health
from app.safety.labels import LABEL_EFFECTS

router = APIRouter(prefix="/under-the-hood", tags=["under-the-hood"])


class LabelItem(BaseModel):
    label: str
    reason: str
    created_at: datetime
    effect: str
    target_type: str
    target_id: str


class UnderTheHoodResponse(BaseModel):
    cred_score: float
    account_labels: list[LabelItem]
    post_label_counts: dict[str, int]
    recent_post_labels: list[LabelItem]
    summary: str


@router.get("", response_model=UnderTheHoodResponse)
async def get_under_the_hood(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UnderTheHoodResponse:
    await refresh_user_health(db, current_user.id)
    user = await db.get(User, current_user.id)
    cred = float(user.cred_score) if user is not None else 50.0

    account_rows = list(
        (
            await db.execute(
                select(SafetyLabel)
                .where(
                    SafetyLabel.target_type == SafetyTargetType.USER,
                    SafetyLabel.target_id == current_user.id,
                )
                .order_by(SafetyLabel.created_at.desc())
            )
        ).scalars().all()
    )
    post_rows = list(
        (
            await db.execute(
                select(SafetyLabel)
                .join(Post, Post.id == SafetyLabel.target_id)
                .where(
                    SafetyLabel.target_type == SafetyTargetType.POST,
                    Post.author_id == current_user.id,
                )
                .order_by(SafetyLabel.created_at.desc())
                .limit(50)
            )
        ).scalars().all()
    )

    def present(row: SafetyLabel) -> LabelItem:
        return LabelItem(
            label=row.label,
            reason=row.reason,
            created_at=row.created_at,
            effect=LABEL_EFFECTS.get(row.label, "可視性に影響する可能性があります。"),
            target_type=row.target_type.value,
            target_id=str(row.target_id),
        )

    counts = Counter(row.label for row in post_rows)
    account_labels = [present(row) for row in account_rows]
    recent = [present(row) for row in post_rows[:20]]

    bits: list[str] = [f"アカウント健全スコア（cred）は {cred:.0f}/100 です。"]
    if account_labels:
        bits.append(
            "アカウントに "
            + "、".join(item.label for item in account_labels)
            + " ラベルがあり、フォロー外への拡散が制限されます。"
        )
    elif not recent:
        bits.append("現在、可視性を制限するラベルは付いていません。")
    if counts:
        bits.append(
            "投稿ラベル: "
            + "、".join(f"{label}×{n}" for label, n in sorted(counts.items()))
        )

    return UnderTheHoodResponse(
        cred_score=cred,
        account_labels=account_labels,
        post_label_counts=dict(counts),
        recent_post_labels=recent,
        summary=" ".join(bits),
    )
