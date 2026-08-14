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


class PostResponse(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    body: str
    visibility: PostVisibility
    status: PostStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowResponse(BaseModel):
    follower_id: uuid.UUID
    followee_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
