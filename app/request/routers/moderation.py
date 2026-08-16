import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Post, User, UserStatus
from app.core.safety_models import SafetyTargetType
from app.request.audit import write_audit_event
from app.request.deps import require_permissions
from app.request.schemas import (
    LabelWriteRequest,
    ModerationActionRequest,
    RoleGrantRequest,
)
from app.safety.labels import upsert_label

router = APIRouter(prefix="/moderation", tags=["moderation"])


@router.post("/posts/{post_id}/hide", status_code=status.HTTP_204_NO_CONTENT)
async def hide_post(
    post_id: uuid.UUID,
    body: ModerationActionRequest,
    request: Request,
    current_user: User = Depends(require_permissions("post.hide")),
    db: AsyncSession = Depends(get_db),
) -> None:
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    post.deleted_at = datetime.now(UTC)
    await write_audit_event(
        db,
        actor_id=current_user.id,
        action="post.hide",
        target_type="post",
        target_id=post.id,
        reason=body.reason,
        ip=request.client.host if request.client else None,
    )
    await db.commit()


@router.post("/users/{user_id}/suspend", status_code=status.HTTP_204_NO_CONTENT)
async def suspend_user(
    user_id: uuid.UUID,
    body: ModerationActionRequest,
    request: Request,
    current_user: User = Depends(require_permissions("user.suspend")),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot suspend self")
    user.status = UserStatus.SUSPENDED
    user.token_version += 1
    await write_audit_event(
        db,
        actor_id=current_user.id,
        action="user.suspend",
        target_type="user",
        target_id=user.id,
        reason=body.reason,
        ip=request.client.host if request.client else None,
    )
    await db.commit()


@router.post("/users/{user_id}/unsuspend", status_code=status.HTTP_204_NO_CONTENT)
async def unsuspend_user(
    user_id: uuid.UUID,
    body: ModerationActionRequest,
    request: Request,
    current_user: User = Depends(require_permissions("user.suspend")),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.status = UserStatus.ACTIVE
    await write_audit_event(
        db,
        actor_id=current_user.id,
        action="user.unsuspend",
        target_type="user",
        target_id=user.id,
        reason=body.reason,
        ip=request.client.host if request.client else None,
    )
    await db.commit()


@router.post("/labels", status_code=status.HTTP_201_CREATED)
async def write_label(
    body: LabelWriteRequest,
    request: Request,
    current_user: User = Depends(require_permissions("label.write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target_type = (
        SafetyTargetType.POST if body.target_type == "post" else SafetyTargetType.USER
    )
    row = await upsert_label(
        db,
        target_type=target_type,
        target_id=body.target_id,
        label=body.label,
        reason=body.reason,
    )
    await write_audit_event(
        db,
        actor_id=current_user.id,
        action="label.write",
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        ip=request.client.host if request.client else None,
        metadata={"label": body.label},
    )
    await db.commit()
    return {
        "id": str(row.id),
        "target_type": body.target_type,
        "target_id": str(body.target_id),
        "label": body.label,
    }


@router.patch("/users/{user_id}/role", status_code=status.HTTP_204_NO_CONTENT)
async def grant_role(
    user_id: uuid.UUID,
    body: RoleGrantRequest,
    request: Request,
    current_user: User = Depends(require_permissions("role.grant")),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    previous = user.role
    user.role = body.role
    await write_audit_event(
        db,
        actor_id=current_user.id,
        action="role.grant",
        target_type="user",
        target_id=user.id,
        reason=body.reason,
        ip=request.client.host if request.client else None,
        metadata={"from": previous, "to": body.role},
    )
    await db.commit()
