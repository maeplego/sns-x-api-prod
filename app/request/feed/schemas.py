import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class FeedPostItem(BaseModel):
    kind: Literal["post"] = "post"
    id: uuid.UUID
    author_id: uuid.UUID
    author_handle: str
    author_display_name: str
    body: str
    created_at: datetime
    rank_score: float | None = None
    parent_id: uuid.UUID | None = None


class WhoToFollowUserItem(BaseModel):
    id: uuid.UUID
    handle: str
    display_name: str
    mutual_follow_count: int
    reason: str = "mutual_follows"


class WhoToFollowModuleItem(BaseModel):
    kind: Literal["who_to_follow"] = "who_to_follow"
    users: list[WhoToFollowUserItem]


FeedItem = Annotated[FeedPostItem | WhoToFollowModuleItem, Field(discriminator="kind")]


class FeedResponse(BaseModel):
    items: list[FeedItem]
    next_cursor: str | None = None
    surface: str = "for_you"


class WhoToFollowResponse(BaseModel):
    users: list[WhoToFollowUserItem]
