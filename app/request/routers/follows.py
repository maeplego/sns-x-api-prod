import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Follow, User
from app.request.auth import get_current_user
from app.request.schemas import FollowResponse

router = APIRouter(prefix="/follows", tags=["follows"])


@router.post("/{user_id}", response_model=FollowResponse, status_code=status.HTTP_201_CREATED)
async def follow_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Follow:
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.followee_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following")

    follow = Follow(follower_id=current_user.id, followee_id=user_id)
    db.add(follow)
    await db.commit()
    await db.refresh(follow)
    return follow


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.followee_id == user_id,
        )
    )
    follow = result.scalar_one_or_none()
    if follow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not following")

    await db.delete(follow)
    await db.commit()
