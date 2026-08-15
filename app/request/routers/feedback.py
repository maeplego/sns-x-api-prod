import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Post, PostStatus, User
from app.core.social_models import FeedbackKind, PostFeedback
from app.request.auth import get_current_user
from app.request.schemas import FeedbackCreateRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/{post_id}", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def upsert_feedback(
    post_id: uuid.UUID,
    payload: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostFeedback:
    post = await db.get(Post, post_id)
    if post is None or post.deleted_at is not None or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.author_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot give feedback on your own post"
        )

    kind = FeedbackKind(payload.kind)
    existing = await db.get(PostFeedback, (current_user.id, post_id))
    if existing is not None:
        existing.kind = kind
        await db.commit()
        await db.refresh(existing)
        if kind == FeedbackKind.HIDE:
            from app.safety.health import refresh_user_health

            await refresh_user_health(db, post.author_id)
        return existing

    row = PostFeedback(viewer_id=current_user.id, post_id=post_id, kind=kind)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    if kind == FeedbackKind.HIDE:
        from app.safety.health import refresh_user_health

        await refresh_user_health(db, post.author_id)
    return row


@router.get("", response_model=list[FeedbackResponse])
async def list_feedback(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PostFeedback]:
    result = await db.execute(
        select(PostFeedback).where(PostFeedback.viewer_id == current_user.id)
    )
    return list(result.scalars().all())


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feedback(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    row = await db.get(PostFeedback, (current_user.id, post_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    await db.delete(row)
    await db.commit()
