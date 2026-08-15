import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Post, User
from app.core.social_models import Notification
from app.request.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])

BODY_PREVIEW_LEN = 140


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


def _clip_body(body: str) -> str:
    text = " ".join(body.split())
    if len(text) <= BODY_PREVIEW_LEN:
        return text
    return text[: BODY_PREVIEW_LEN - 1] + "…"


async def _post_previews(db: AsyncSession, post_ids: list[uuid.UUID]) -> dict[str, str]:
    if not post_ids:
        return {}
    rows = await db.execute(select(Post.id, Post.body).where(Post.id.in_(post_ids)))
    return {str(post_id): _clip_body(body) for post_id, body in rows.all()}


def _like_key(item: Notification) -> str:
    payload = item.payload_json or {}
    return str(payload.get("liker_id") or payload.get("liker_handle") or item.id)


async def _present_notifications(
    db: AsyncSession, items: list[Notification]
) -> list[NotificationItem]:
    like_groups: dict[str, list[Notification]] = {}
    order: list[tuple[str, str]] = []
    others: dict[str, Notification] = {}

    for item in items:
        if item.type == "post_liked":
            key = _like_key(item)
            if key not in like_groups:
                like_groups[key] = []
                order.append(("like", key))
            like_groups[key].append(item)
        else:
            other_key = str(item.id)
            others[other_key] = item
            order.append(("other", other_key))

    post_ids: list[uuid.UUID] = []
    for group in like_groups.values():
        for item in group:
            raw = (item.payload_json or {}).get("post_id")
            if not raw:
                continue
            try:
                post_ids.append(uuid.UUID(str(raw)))
            except ValueError:
                continue
    previews = await _post_previews(db, post_ids)

    presented: list[NotificationItem] = []
    for kind, key in order:
        if kind == "other":
            presented.append(NotificationItem.model_validate(others[key]))
            continue
        group = like_groups[key]
        newest = group[0]
        posts: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in group:
            post_id = str((item.payload_json or {}).get("post_id") or "")
            if not post_id or post_id in seen:
                continue
            seen.add(post_id)
            posts.append({"id": post_id, "body": previews.get(post_id, "")})
        payload = dict(newest.payload_json or {})
        payload["posts"] = posts
        presented.append(
            NotificationItem(
                id=newest.id,
                type="post_liked",
                payload_json=payload,
                read_at=None if any(item.read_at is None for item in group) else newest.read_at,
                created_at=newest.created_at,
            )
        )
    return presented


@router.get("", response_model=NotificationsResponse)
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=100),
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
    return NotificationsResponse(
        items=await _present_notifications(db, items),
        unread_count=int(unread or 0),
    )


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
