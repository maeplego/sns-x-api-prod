import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FeedPostItem(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    author_handle: str
    author_display_name: str
    body: str
    created_at: datetime


class FeedResponse(BaseModel):
    items: list[FeedPostItem]
    next_cursor: str | None = None
