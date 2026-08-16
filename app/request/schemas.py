import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

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
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class SignupResponse(TokenResponse):
    """Signup returns the token pair plus the created user (for clients/tests)."""

    id: uuid.UUID
    handle: str
    email: EmailStr
    display_name: str
    bio: str | None = None
    is_private: bool = False
    status: UserStatus = UserStatus.ACTIVE
    role: str = "user"
    created_at: datetime


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class AccountEraseRequest(BaseModel):
    password: str


class ReportCreateRequest(BaseModel):
    target_type: str = Field(pattern="^(post|user)$")
    target_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=2000)


class ReportResolveRequest(BaseModel):
    status: str = Field(pattern="^(resolved|dismissed)$")
    reason: str | None = Field(default=None, max_length=2000)


class ReportResponse(BaseModel):
    id: uuid.UUID
    reporter_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reason: str
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
    resolver_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class ModerationActionRequest(BaseModel):
    reason: str = Field(default="", max_length=2000)


class LabelWriteRequest(BaseModel):
    target_type: str = Field(pattern="^(post|user)$")
    target_id: uuid.UUID
    label: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=2000)


class RoleGrantRequest(BaseModel):
    role: str = Field(pattern="^(user|moderator|admin)$")
    reason: str = Field(default="", max_length=2000)


class UserResponse(BaseModel):
    id: uuid.UUID
    handle: str
    email: EmailStr
    display_name: str
    bio: str | None
    is_private: bool
    status: UserStatus
    role: str = "user"
    created_at: datetime

    model_config = {"from_attributes": True}


class UserPublicResponse(BaseModel):
    id: uuid.UUID
    handle: str
    display_name: str
    bio: str | None
    is_private: bool
    status: UserStatus
    created_at: datetime
    follower_count: int = 0
    following_count: int = 0
    is_following: bool = False
    is_self: bool = False
    is_blocking: bool = False
    is_muting: bool = False

    model_config = {"from_attributes": True}


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    bio: str | None = Field(default=None, max_length=500)
    is_private: bool | None = None


class PostCreateRequest(BaseModel):
    body: str = Field(default="", max_length=2000)
    visibility: PostVisibility = PostVisibility.PUBLIC
    parent_id: uuid.UUID | None = None
    quote_of_id: uuid.UUID | None = None
    repost_of_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_body_and_refs(self):
        refs = [self.parent_id, self.quote_of_id, self.repost_of_id]
        if sum(value is not None for value in refs) > 1:
            raise ValueError("parent_id, quote_of_id, and repost_of_id are mutually exclusive")
        if self.repost_of_id is not None:
            object.__setattr__(self, "body", "")
            return self
        if not self.body.strip():
            raise ValueError("body is required")
        return self


class PostResponse(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    body: str
    visibility: PostVisibility
    status: PostStatus
    parent_id: uuid.UUID | None = None
    root_id: uuid.UUID | None = None
    quote_of_id: uuid.UUID | None = None
    repost_of_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReferencedPostItem(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID | None = None
    author_handle: str
    author_display_name: str
    body: str


class PostCardItem(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    author_handle: str
    author_display_name: str
    body: str
    created_at: datetime
    parent_id: uuid.UUID | None = None
    parent_author_handle: str | None = None
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    liked: bool = False
    reposted: bool = False
    quote_of: ReferencedPostItem | None = None
    repost_of: ReferencedPostItem | None = None


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
    items: list[PostCardItem]


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


class UserListItem(BaseModel):
    id: uuid.UUID
    handle: str
    display_name: str
    bio: str | None
    is_following: bool = False


class UserListResponse(BaseModel):
    items: list[UserListItem]
    next_cursor: str | None = None


class PostListResponse(BaseModel):
    items: list[PostCardItem]
    next_cursor: str | None = None


class SearchResponse(BaseModel):
    users: list[UserListItem]
    posts: list[PostCardItem]


class FeedUpdatesResponse(BaseModel):
    has_new: bool
    count: int


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
