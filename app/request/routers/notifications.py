import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import User
from app.core.social_models import Notification
from app.request.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationItem(BaseModel):
    id: uuid.UUID
    type: str
    payload_json: dict
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationsResponse(BaseModel):
    items: list[NotificationItem]
    unread_count: int


class MarkReadResponse(BaseModel):
    updated: int


@router.get("", response_model=NotificationsResponse)
async def list_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationsResponse:
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    items = list(result.scalars().all())
    unread = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
    )
    return NotificationsResponse(items=items, unread_count=int(unread or 0))


@router.post("/read", response_model=MarkReadResponse)
async def mark_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarkReadResponse:
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()
    return MarkReadResponse(updated=result.rowcount or 0)
