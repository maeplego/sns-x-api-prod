import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import User
from app.core.social_models import MutedKeyword
from app.request.auth import get_current_user
from app.request.schemas import MutedKeywordCreateRequest, MutedKeywordResponse

router = APIRouter(prefix="/muted-keywords", tags=["muted-keywords"])


@router.post("", response_model=MutedKeywordResponse, status_code=status.HTTP_201_CREATED)
async def create_muted_keyword(
    payload: MutedKeywordCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MutedKeyword:
    existing = await db.execute(
        select(MutedKeyword).where(
            MutedKeyword.user_id == current_user.id,
            MutedKeyword.keyword == payload.keyword,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Keyword already muted")

    row = MutedKeyword(user_id=current_user.id, keyword=payload.keyword)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("", response_model=list[MutedKeywordResponse])
async def list_muted_keywords(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MutedKeyword]:
    result = await db.execute(
        select(MutedKeyword).where(MutedKeyword.user_id == current_user.id)
    )
    return list(result.scalars().all())


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_muted_keyword(
    keyword_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(MutedKeyword).where(
            MutedKeyword.id == keyword_id,
            MutedKeyword.user_id == current_user.id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword not found")

    await db.delete(row)
    await db.commit()
