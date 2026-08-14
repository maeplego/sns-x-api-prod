import base64
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.core.models import PostVisibility, UserStatus


@dataclass
class FeedQuery:
    viewer_id: uuid.UUID
    following_ids: set[uuid.UUID] = field(default_factory=set)
    blocked_user_ids: set[uuid.UUID] = field(default_factory=set)
    cursor: tuple[datetime, uuid.UUID] | None = None
    limit: int = 20


@dataclass
class FeedCandidate:
    id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime
    visibility: PostVisibility = PostVisibility.PUBLIC
    author_handle: str | None = None
    author_display_name: str | None = None
    author_is_private: bool = False
    author_status: UserStatus = UserStatus.ACTIVE
    like_count: int = 0
    reply_count: int = 0
    author_affinity: float = 0.0
    seen: bool = False
    rank_score: float | None = None


def encode_cursor(created_at: datetime, post_id: uuid.UUID) -> str:
    payload = {"created_at": created_at.isoformat(), "post_id": str(post_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(payload["created_at"]), uuid.UUID(payload["post_id"])
