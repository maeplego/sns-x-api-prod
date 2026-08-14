import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Post, PostStatus, User
from app.request.auth import get_current_user
from app.request.schemas import PostResponse, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/{handle}", response_model=UserResponse)
async def get_user_by_handle(handle: str, db: AsyncSession = Depends(get_db)) -> User:
    result = await db.execute(select(User).where(User.handle == handle.lower()))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/{handle}/posts", response_model=list[PostResponse])
async def get_user_posts(handle: str, db: AsyncSession = Depends(get_db)) -> list[Post]:
    result = await db.execute(select(User).where(User.handle == handle.lower()))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    posts = await db.execute(
        select(Post)
        .where(
            Post.author_id == user.id,
            Post.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
            Post.parent_id.is_(None),
        )
        .order_by(Post.created_at.desc())
    )
    return list(posts.scalars().all())
