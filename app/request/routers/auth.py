from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.legal import PRIVACY_VERSION, TERMS_VERSION
from app.core.models import User, UserStatus
from app.request.auth import (
    get_current_user,
    hash_password,
    issue_token_pair,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)
from app.request.rate_limit import rate_limit
from app.request.schemas import (
    LoginRequest,
    LogoutRequest,
    PasswordChangeRequest,
    RefreshRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("signup", limit=5))],
)
async def signup(
    body: SignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SignupResponse:
    existing = await db.execute(
        select(User).where((User.email == body.email) | (User.handle == body.handle))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email or handle taken")

    now = datetime.now(UTC)
    user = User(
        handle=body.handle,
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        status=UserStatus.ACTIVE,
        role="user",
        token_version=0,
        terms_version=TERMS_VERSION,
        privacy_version=PRIVACY_VERSION,
        terms_accepted_at=now,
        privacy_accepted_at=now,
    )
    db.add(user)
    await db.flush()
    user_agent = request.headers.get("user-agent")
    tokens = await issue_token_pair(user, db, user_agent=user_agent)
    return SignupResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        id=user.id,
        handle=user.handle,
        email=user.email,
        display_name=user.display_name,
        bio=user.bio,
        is_private=user.is_private,
        status=user.status,
        role=user.role,
        created_at=user.created_at,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("login", limit=10))],
)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")

    user_agent = request.headers.get("user-agent")
    return await issue_token_pair(user, db, user_agent=user_agent)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user_agent = request.headers.get("user-agent")
    return await rotate_refresh_token(db, body.refresh_token, user_agent=user_agent)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    if body is not None and body.refresh_token:
        await revoke_refresh_token(db, body.refresh_token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    current_user.token_version += 1
    await revoke_all_refresh_tokens(db, current_user.id)
    await db.commit()


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong password")
    current_user.password_hash = hash_password(body.new_password)
    current_user.token_version += 1
    await revoke_all_refresh_tokens(db, current_user.id)
    await db.commit()
