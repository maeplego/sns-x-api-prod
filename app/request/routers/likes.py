import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Post, PostEngagement, PostStatus, User
from app.core.social_models import Like, Notification
from app.request.auth import get_current_user

router = APIRouter(prefix="/likes", tags=["likes"])


@router.post("/{post_id}", status_code=status.HTTP_201_CREATED)
async def like_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    post = await db.get(Post, post_id)
    if post is None or post.deleted_at is not None or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.repost_of_id is not None:
        original = await db.get(Post, post.repost_of_id)
        if original is None or original.deleted_at is not None or original.status != PostStatus.PUBLISHED:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        post = original
        post_id = post.id
    if post.author_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot like your own post")

    existing = await db.execute(
        select(Like).where(Like.user_id == current_user.id, Like.post_id == post_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already liked")

    db.add(Like(user_id=current_user.id, post_id=post_id))

    engagement = await db.get(PostEngagement, post_id)
    if engagement is None:
        engagement = PostEngagement(post_id=post_id, like_count=1, reply_count=0, repost_count=0)
        db.add(engagement)
    else:
        engagement.like_count += 1

    db.add(
        Notification(
            user_id=post.author_id,
            type="post_liked",
            payload_json={
                "post_id": str(post_id),
                "post_body": post.body[:140],
                "liker_id": str(current_user.id),
                "liker_handle": current_user.handle,
            },
        )
    )
    await db.commit()
    return {"status": "liked"}


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Like).where(Like.user_id == current_user.id, Like.post_id == post_id)
    )
    like = result.scalar_one_or_none()
    if like is None:
        post = await db.get(Post, post_id)
        if post is not None and post.repost_of_id is not None:
            result = await db.execute(
                select(Like).where(
                    Like.user_id == current_user.id,
                    Like.post_id == post.repost_of_id,
                )
            )
            like = result.scalar_one_or_none()
            if like is not None:
                post_id = post.repost_of_id
    if like is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not liked")

    await db.delete(like)
    engagement = await db.get(PostEngagement, post_id)
    if engagement is not None and engagement.like_count > 0:
        engagement.like_count -= 1
    await db.commit()
