from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import User
from app.request.auth import get_current_user
from app.request.feed.pipeline import build_feed_pipeline
from app.request.feed.schemas import FeedPostItem, FeedResponse
from app.request.feed.types import FeedQuery, decode_cursor

router = APIRouter(tags=["feed"])
pipeline = build_feed_pipeline()


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    parsed_cursor = None
    if cursor is not None:
        try:
            parsed_cursor = decode_cursor(cursor)
        except (ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor",
            ) from exc

    query = FeedQuery(viewer_id=current_user.id, cursor=parsed_cursor, limit=limit)
    candidates, next_cursor = await pipeline.run(db, query)

    items = [
        FeedPostItem(
            id=c.id,
            author_id=c.author_id,
            author_handle=c.author_handle or "unknown",
            author_display_name=c.author_display_name or "Unknown",
            body=c.body,
            created_at=c.created_at,
        )
        for c in candidates
    ]
    return FeedResponse(items=items, next_cursor=next_cursor)
