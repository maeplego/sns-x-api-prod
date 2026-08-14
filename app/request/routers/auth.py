from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import User, UserStatus
from app.request.auth import create_access_token, hash_password, verify_password
from app.request.schemas import LoginRequest, SignupRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)) -> User:
    existing = await db.execute(
        select(User).where((User.email == body.email) | (User.handle == body.handle))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email or handle taken")

    user = User(
        handle=body.handle,
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token)
