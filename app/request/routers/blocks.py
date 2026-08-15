import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Block, Follow, User
from app.request.auth import get_current_user
from app.request.feed.backfill import remove_followee_from_feed
from app.request.schemas import BlockResponse

router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.post("/{user_id}", response_model=BlockResponse, status_code=status.HTTP_201_CREATED)
async def block_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Block:
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot block yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = await db.execute(
        select(Block).where(
            Block.blocker_id == current_user.id,
            Block.blocked_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already blocked")

    follows = await db.execute(
        select(Follow).where(
            or_(
                (Follow.follower_id == current_user.id) & (Follow.followee_id == user_id),
                (Follow.follower_id == user_id) & (Follow.followee_id == current_user.id),
            )
        )
    )
    for follow in follows.scalars().all():
        await remove_followee_from_feed(db, follow.follower_id, follow.followee_id)
        await db.delete(follow)

    block = Block(blocker_id=current_user.id, blocked_id=user_id)
    db.add(block)
    await db.commit()
    await db.refresh(block)
    from app.safety.health import refresh_user_health

    await refresh_user_health(db, user_id)
    return block


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Block).where(
            Block.blocker_id == current_user.id,
            Block.blocked_id == user_id,
        )
    )
    block = result.scalar_one_or_none()
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not blocked")

    await db.delete(block)
    await db.commit()
