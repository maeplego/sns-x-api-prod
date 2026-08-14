import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.models import PostStatus, PostVisibility, UserStatus

HANDLE_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class SignupRequest(BaseModel):
    handle: str = Field(min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=64)

    @field_validator("handle")
    @classmethod
    def validate_handle(cls, value: str) -> str:
        if not HANDLE_PATTERN.match(value):
            raise ValueError("handle must be 3-32 chars: letters, numbers, underscore")
        return value.lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    handle: str
    email: EmailStr
    display_name: str
    bio: str | None
    is_private: bool
    status: UserStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class PostCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    visibility: PostVisibility = PostVisibility.PUBLIC
    parent_id: uuid.UUID | None = None


class PostResponse(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    body: str
    visibility: PostVisibility
    status: PostStatus
    parent_id: uuid.UUID | None = None
    root_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ThreadPostItem(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    author_handle: str
    author_display_name: str
    body: str
    parent_id: uuid.UUID | None
    created_at: datetime


class ThreadResponse(BaseModel):
    root_id: uuid.UUID
    items: list[ThreadPostItem]


class PostAcceptedResponse(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    status: PostStatus
    message: str = "Post accepted for processing"


class FollowResponse(BaseModel):
    follower_id: uuid.UUID
    followee_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class BlockResponse(BaseModel):
    blocker_id: uuid.UUID
    blocked_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class MuteResponse(BaseModel):
    muter_id: uuid.UUID
    muted_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class MutedKeywordCreateRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=64)

    @field_validator("keyword")
    @classmethod
    def normalize_keyword(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("keyword must not be blank")
        return normalized


class MutedKeywordResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    keyword: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackCreateRequest(BaseModel):
    kind: str = Field(pattern="^(hide|not_interested)$")


class FeedbackResponse(BaseModel):
    viewer_id: uuid.UUID
    post_id: uuid.UUID
    kind: str
    created_at: datetime

    model_config = {"from_attributes": True}
