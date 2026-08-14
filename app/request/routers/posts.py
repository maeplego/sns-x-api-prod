import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Post, PostStatus, User
from app.core.queue import get_event_bus
from app.labeling.events import POST_CREATED
from app.request.auth import get_current_user, get_optional_user
from app.request.schemas import PostAcceptedResponse, PostCreateRequest, PostResponse

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("", response_model=PostAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_post(
    body: PostCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostAcceptedResponse:
    post = Post(
        author_id=current_user.id,
        body=body.body,
        visibility=body.visibility,
        status=PostStatus.PROCESSING,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    await get_event_bus().publish(
        POST_CREATED,
        {"post_id": str(post.id), "author_id": str(current_user.id)},
    )

    return PostAcceptedResponse(
        id=post.id,
        author_id=post.author_id,
        status=post.status,
    )


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> Post:
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.deleted_at.is_(None))
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if post.status != PostStatus.PUBLISHED:
        if current_user is None or current_user.id != post.author_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.deleted_at.is_(None))
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your post")

    post.deleted_at = datetime.now(UTC)
    await db.commit()
