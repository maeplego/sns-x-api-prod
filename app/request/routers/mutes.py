import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Mute, User
from app.request.auth import get_current_user
from app.request.schemas import MuteResponse

router = APIRouter(prefix="/mutes", tags=["mutes"])


@router.post("/{user_id}", response_model=MuteResponse, status_code=status.HTTP_201_CREATED)
async def mute_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Mute:
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot mute yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = await db.execute(
        select(Mute).where(
            Mute.muter_id == current_user.id,
            Mute.muted_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already muted")

    mute = Mute(muter_id=current_user.id, muted_id=user_id)
    db.add(mute)
    await db.commit()
    await db.refresh(mute)
    return mute


@router.get("", response_model=list[MuteResponse])
async def list_mutes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Mute]:
    result = await db.execute(select(Mute).where(Mute.muter_id == current_user.id))
    return list(result.scalars().all())


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unmute_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Mute).where(
            Mute.muter_id == current_user.id,
            Mute.muted_id == user_id,
        )
    )
    mute = result.scalar_one_or_none()
    if mute is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not muted")

    await db.delete(mute)
    await db.commit()
